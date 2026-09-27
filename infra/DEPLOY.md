# Deploying the FormIQ backend on AWS (free tier, beginner guide)

Written for someone who has never deployed on AWS. Every command is
copy-pasteable. Design rationale lives in
`docs/superpowers/specs/2026-09-27-backend-deployment-design.md`.

**What you are building:** the FastAPI backend running on one small Linux
server on the internet, with the workout database on a disk that survives
restarts. The React frontend keeps running on your laptop and talks to
that server. The frontend is deliberately *not* deployed — see "Why the
frontend stays local" at the bottom.

**Roughly how long:** about an hour the first time, most of it waiting.

**What it costs:** $0 for 12 months on a new AWS account, if you stay
inside the limits this guide sticks to. Read "The free tier, honestly"
next — that section is the whole point of this version.

---

## The free tier, honestly

A new AWS account gets, for **12 months from signup**:

- **750 hours/month of a `t3.micro` instance** — enough to run one
  continuously, all month.
- **30 GB of EBS disk** (we use 20).
- **750 hours/month of a public IPv4 address** — which matters, because
  AWS charges for public IPv4 addresses (~$3.60/month) once that runs out.
- 100 GB/month of outbound data transfer, far more than you'll use.

Two things to be clear-eyed about:

1. **After 12 months this instance costs roughly $11–12/month** (instance +
   IPv4 + disk). It does not stop or warn you; it starts billing. Put a
   calendar reminder at 11 months to delete it or decide to pay.
2. **AWS has been reworking the free tier.** Newer accounts may instead get
   signup credits with an expiry rather than the classic 12-month
   allowances. I can't see which applies to your account. Check
   <https://aws.amazon.com/free> and trust the console's green **"Free tier
   eligible"** label over anything written here.

**The real constraint: `t3.micro` has 1 GB of RAM.** Your ingestion path
decodes video with OpenCV and runs two LiteRT pose models, which is a tight
fit. Step 7 adds a swap file so the kernel pages to disk instead of killing
the process. It's slower than real RAM, but it means analysis completes
rather than dying. If it's too slow to tolerate, the fix is a paid
instance with 2 GB.

Step 1's budget alarm is not optional. Free tiers end quietly.

---

## Step 0 — Push your code to GitHub

The server downloads a prebuilt image that GitHub Actions makes for you.
That can't happen until your commits are on GitHub.

```sh
git push origin main
```

Now open <https://github.com/etctran/FormIQ/actions>. A workflow called
**"Build backend image"** should be running. **It will take 10–20 minutes**
— it compiles the C++ pose engine and LiteRT from source. Let it run while
you do the next steps.

> If it fails, stop and fix that first. Nothing below works without an
> image. The most likely cause is a build error in `cv-engine`.

---

## Step 1 — Protect yourself from a surprise bill

Do this before creating anything.

1. Sign in at <https://console.aws.amazon.com>.
2. Search the top bar for **Billing and Cost Management** → open it.
3. Sidebar: **Budgets** → **Create budget**.
4. Choose **Use a template (simplified)** → **Monthly cost budget**.
5. Amount **5** (dollars), enter your email, create it.

Five, not twenty: if you're inside the free tier you should be at or near
$0, so any real charge means something's misconfigured and you want to hear
about it immediately.

---

## Step 2 — Launch the server

1. Go to <https://console.aws.amazon.com/ec2>.
2. **Top-right: check your region** (e.g. "N. Virginia"). Pick one near you
   and remember it — EC2 resources are per-region, and a common beginner
   confusion is "my instance vanished" when the console is just showing a
   different region.
3. Click the orange **Launch instance**.

Then, working down the form:

- **Name:** `formiq-backend`
- **Application and OS Images:** select **Ubuntu**, then choose
  **Ubuntu Server 24.04 LTS**. Confirm it shows a green
  **"Free tier eligible"** tag.
- **Instance type:** `t3.micro` — it should also be tagged **"Free tier
  eligible"**. If it isn't in your region, `t2.micro` will be; take
  whichever carries the label.
- **Key pair (login):** click **Create new key pair**. Name it
  `formiq-key`, type **RSA**, format **.pem**. It downloads once — keep it
  somewhere you won't lose it. You'll mostly use browser SSH instead
  (Step 5), but you need a key pair to launch and it's your fallback.
- **Network settings** → click **Edit**, then:
  - **Allow SSH traffic from** → choose **My IP** (not "Anywhere").
  - Click **Add security group rule**:
    - Type **Custom TCP**, **Port range** `8000`, **Source type** **My IP**.
  - This is your firewall. Port 22 to let you in, port 8000 for the API,
    both restricted to your own address.
- **Configure storage:** change `8` GiB to **20** GiB, type **gp3**. Still
  well inside the 30 GB free allowance, and 8 GiB is uncomfortably tight
  once the image is pulled.

Click **Launch instance**, then **View all instances**. Wait until
**Instance state** is "Running" and **Status check** passes (a minute or
two).

---

## Step 3 — Give it an address that doesn't change

By default the public IP changes every time the instance stops and starts,
which would break your frontend config.

1. EC2 sidebar → **Elastic IPs** (under Network & Security).
2. **Allocate Elastic IP address** → **Allocate**.
3. Select it → **Actions** → **Associate Elastic IP address**.
4. Choose your `formiq-backend` instance → **Associate**.

**Write this address down.** It's `<YOUR-IP>` below.

> An Elastic IP is free **only while attached to a running instance**. If
> you later stop or delete the instance but keep the address, it starts
> costing money. Release it when you're done (Step 12).

---

## Step 4 — Confirm the firewall

You set this during launch; this is just the place to fix it later.

EC2 → **Instances** → select yours → **Security** tab → click the security
group → **Inbound rules**. You should see SSH (22) and Custom TCP (8000),
each with your own IP as the source.

> **Home internet IPs change.** If the API starts timing out after a few
> days, this is almost always why — not a broken server. Get your current
> address from <https://checkip.amazonaws.com>, then **Edit inbound rules**
> and update both entries (or re-pick **My IP**).

---

## Step 5 — Connect to the server

EC2 → **Instances** → select yours → **Connect** button → **EC2 Instance
Connect** tab → **Connect**. A terminal opens in your browser. No key file
needed.

<details>
<summary>If EC2 Instance Connect doesn't work, use the key file</summary>

From your laptop's terminal, in the folder holding `formiq-key.pem`:

```sh
chmod 400 formiq-key.pem
ssh -i formiq-key.pem ubuntu@<YOUR-IP>
```

`chmod 400` is required — SSH refuses keys that other users could read.
</details>

Everything in Steps 6–9 is typed into that server terminal.

---

## Step 6 — Install Docker

```sh
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2
sudo usermod -aG docker "$USER"
```

Now **disconnect and reconnect** (close the tab, hit Connect again). The
last command only takes effect on a fresh login. Verify:

```sh
docker ps
```

An empty table with headers = success. `permission denied` = you didn't
reconnect.

---

## Step 7 — Add swap (the 1 GB workaround)

This is the step that makes a free-tier instance viable for video
processing. Without it, analysing a video can get the process killed
outright.

```sh
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

The last line makes it survive reboots. Check it:

```sh
free -h
```

You should see a `Swap:` row showing 2.0Gi. Now the machine has 1 GB of
real memory plus 2 GB of slower disk-backed overflow.

---

## Step 8 — Let the server download your image

GitHub Container Registry images are private by default, so the server
needs read permission.

**On your laptop:** create a token at
<https://github.com/settings/tokens> → **Generate new token (classic)**.
Name it `formiq-server`, expiry 90 days, tick **only** `read:packages`.
Generate and copy the `ghp_...` string — GitHub shows it once.

**In the server terminal**, with your token pasted in:

```sh
echo 'ghp_YOUR_TOKEN_HERE' | docker login ghcr.io -u etctran --password-stdin
```

Expect `Login Succeeded`.

---

## Step 9 — Create the config

```sh
sudo mkdir -p /opt/formiq/data
sudo chown -R "$USER" /opt/formiq
cd /opt/formiq
```

Generate a random password for your API and save it:

```sh
KEY=$(openssl rand -hex 32)
cat > .env <<EOF
IMAGE=ghcr.io/etctran/formiq/backend:latest
FORMIQ_API_KEY=$KEY
EOF
cat .env
```

**Copy the `FORMIQ_API_KEY` value that prints** — your laptop needs the
identical string in Step 11.

Now the compose file (mirrors `infra/docker-compose.prod.yml`):

```sh
cat > docker-compose.prod.yml <<'EOF'
services:
  backend:
    image: ${IMAGE}
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      FORMIQ_DB_PATH: /data/formiq.db
      FORMIQ_API_KEY: ${FORMIQ_API_KEY:?set FORMIQ_API_KEY in .env}
    volumes:
      - /opt/formiq/data:/data
EOF
```

Two lines there are the whole durability story: `FORMIQ_DB_PATH` puts the
database at `/data/formiq.db` inside the container, and `volumes` makes
`/data` actually be `/opt/formiq/data` on the real disk. Destroy and
recreate the container freely — the database is outside it.

`restart: unless-stopped` brings the container back by itself after a
reboot.

---

## Step 10 — Start it

Check the GitHub Actions run from Step 0 finished green, then:

```sh
cd /opt/formiq
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

The pull downloads a large image — several minutes on a small instance.
Then:

```sh
curl -f http://localhost:8000/health
```

Expect `{"status":"ok"}`. If not, the logs say why:

```sh
docker compose -f docker-compose.prod.yml logs
```

---

## Step 11 — Check it from your laptop

On **your own machine**, substituting your values:

```sh
# 1. Health check needs no key — proves the server is reachable
curl http://<YOUR-IP>:8000/health

# 2. No key on a real endpoint must be refused — proves the guard works
curl -o /dev/null -w '%{http_code}\n' http://<YOUR-IP>:8000/history

# 3. With the key it must work — proves the key is right
curl -H "X-API-Key: <YOUR-KEY>" http://<YOUR-IP>:8000/history
```

Expected: `{"status":"ok"}`, then `401`, then `[]` (or your entries).

Reading failures:

- **All three hang** → firewall or region. Step 4, and re-check your IP.
- **#2 returns `200`** → `FORMIQ_API_KEY` never reached the container.
  Check `.env`, then re-run `up -d`.
- **#3 returns `401`** → your laptop's key doesn't match the server's.
  Re-read it with `cat /opt/formiq/.env`.
- **Analysis requests die or the container restarts** → memory. Confirm
  swap is on with `free -h` (Step 7), and watch it with
  `docker stats` during an upload.

Then point the frontend at it: create `frontend/.env.local` on your laptop
(gitignored, never committed):

```
VITE_API_BASE_URL=http://<YOUR-IP>:8000
VITE_API_KEY=<YOUR-KEY>
```

Run `npm run dev` from `frontend/` as usual. Uploads now go to the server.

---

## Deploying again later

Every push to `main` rebuilds the image. To pick it up:

```sh
cd /opt/formiq
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

A few seconds of downtime. The database is untouched — it's on the disk,
not in the container.

---

## Step 12 — Shutting it down

Back up first:

```sh
sudo apt-get install -y sqlite3    # not installed by default
sqlite3 /opt/formiq/data/formiq.db ".backup /tmp/backup.db"
```

Copy `/tmp/backup.db` to your laptop:

```sh
# from your laptop
scp -i formiq-key.pem ubuntu@<YOUR-IP>:/tmp/backup.db .
```

Then, to stop all charges, do **both**:

1. EC2 → **Instances** → select → **Instance state** → **Terminate**.
   (*Stop* keeps the disk and keeps billing for it. *Terminate* deletes it.)
2. EC2 → **Elastic IPs** → select → **Actions** → **Release**. An
   unattached Elastic IP is billed.

Leaving the Elastic IP behind is the single most common way people keep
paying AWS for a project they thought they deleted.

---

## Backups

Not automated. The `.backup` command above on a cron is the simple option:

```sh
# once a day at 3am, keeping the last 7
(crontab -l 2>/dev/null; echo '0 3 * * * sqlite3 /opt/formiq/data/formiq.db ".backup /opt/formiq/data/backup-$(date +\%u).db"') | crontab -
```

Use `.backup` rather than copying the file — it's safe against a write
happening mid-copy.

---

## Why the frontend stays local

Vite bakes `VITE_*` values into the JavaScript bundle at build time. A
publicly served frontend would therefore ship `VITE_API_KEY` in plain text
to anyone who loaded the page, making the API guard pointless. Serving it
properly needs real login accounts, a domain and HTTPS — a much bigger
project. Running `npm run dev` locally costs nothing and keeps the key on
your machine.

---

## Glossary

- **EC2** — AWS's virtual servers. An "instance" is one server.
- **AMI** — the OS image an instance starts from (here: Ubuntu 24.04).
- **`t3.micro`** — the instance size. 2 vCPUs, 1 GB RAM, free-tier eligible.
- **Security group** — a firewall attached to your instance. Inbound rules
  say who may connect to which port.
- **Elastic IP** — an address that stays the same across stop/start.
- **EBS** — the virtual hard disk attached to the instance. Persists
  independently of the container; this is where your database lives.
- **Swap** — disk space used as overflow when RAM runs out. Slow, but
  prevents processes being killed.
- **Image** — a frozen snapshot of your app and its dependencies, built by
  GitHub Actions and downloaded by the server.
- **Container** — a running copy of an image. Disposable; anything written
  inside it vanishes when replaced, which is why the database is on a
  mounted volume.
- **GHCR** — GitHub Container Registry, where your built images are stored.
- **`My IP` / `/32`** — in a firewall rule, "exactly my one address".
