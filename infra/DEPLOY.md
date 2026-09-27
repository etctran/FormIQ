# Deploying the FormIQ backend (beginner guide)

Written for someone who has never deployed on AWS. Every command is
copy-pasteable. Design rationale lives in
`docs/superpowers/specs/2026-09-27-backend-deployment-design.md`.

**What you are building:** the FastAPI backend running on one small Linux
server on the internet, with the workout database on a disk that survives
restarts. The React frontend keeps running on your laptop and talks to
that server. The frontend is deliberately *not* deployed — see "Why the
frontend stays local" at the bottom.

**Roughly how long:** 45–60 minutes the first time, most of it waiting.

**What it costs:** about **$12/month**, fixed. Step 1 sets up a safety net
so it cannot surprise you.

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
> image. The most common cause is a build error in `cv-engine`.

---

## Step 1 — Protect yourself from a surprise bill

Do this before creating anything. AWS will happily let you spend money by
accident, and every beginner horror story starts here.

1. Sign in at <https://console.aws.amazon.com>.
2. Search the top bar for **Billing and Cost Management** → open it.
3. In the left sidebar: **Budgets** → **Create budget**.
4. Choose **Use a template (simplified)** → **Monthly cost budget**.
5. Set the amount to **20** (dollars), enter your email, and create it.

You will now get an email if you ever approach $20/month. The setup below
should sit around $12.

---

## Step 2 — Create the server (Lightsail)

Lightsail is AWS's beginner-friendly server product. Same machines as EC2,
but one fixed monthly price and far fewer decisions.

1. Go to <https://lightsail.aws.amazon.com>.
2. Click **Create instance**.
3. **Region:** pick the one closest to you (e.g. `us-east-1` Virginia,
   `us-west-2` Oregon). Don't overthink it; you can't change it later
   without rebuilding.
4. **Platform:** Linux/Unix.
5. **Blueprint:** choose **OS Only** → **Ubuntu 24.04 LTS**.
   *Not* one of the app blueprints — you want a plain machine.
6. **Instance plan:** choose the **$12/month** one (2 GB RAM, 2 vCPUs,
   60 GB SSD). The cheapest plan has too little memory for video
   processing. If video analysis later dies with "killed" or an
   out-of-memory error in the logs, upgrade to the $24 plan (4 GB) —
   Lightsail can resize from a snapshot.

   *(Plan names and prices are what Lightsail offered as of writing;
   check the page for current numbers.)*
7. **Name:** `formiq-backend`.
8. Click **Create instance**. It takes a minute or two to say "Running".

The 60 GB SSD is what makes your database durable — it's a real disk
attached to the instance, not temporary scratch space.

---

## Step 3 — Give it an address that doesn't change

By default the server's IP address changes every time it restarts, which
would break your frontend config.

1. In Lightsail, open the **Networking** tab (top of the page, not inside
   the instance).
2. **Create static IP**.
3. Attach it to `formiq-backend`, name it `formiq-ip`, click **Create**.

**Write this IP address down.** It's referred to below as `<YOUR-IP>`.
Static IPs are free while attached to a running instance.

---

## Step 4 — Open the right port, to only you

Your API should be reachable by you and nobody else.

First find your own IP: visit <https://checkip.amazonaws.com> and note
the number.

1. In Lightsail, click your instance → **Networking** tab.
2. Under **IPv4 Firewall**, click **Add rule**.
3. **Application:** Custom · **Protocol:** TCP · **Port:** `8000`.
4. Tick **Restrict to IP address** and enter the IP from
   checkip.amazonaws.com, followed by `/32`
   (for example `203.0.113.7/32` — the `/32` means "exactly this one
   address").
5. **Create**.

Leave the existing SSH rule (port 22) alone.

> **Home internet IPs change.** If the API stops responding in a few days
> with a timeout, re-check checkip.amazonaws.com and update this rule.
> That's the usual cause, not a broken server.

---

## Step 5 — Connect to the server

In Lightsail, click your instance → the orange **Connect using SSH**
button. A terminal opens in your browser. No keys, no config.

Everything in Steps 6–9 is typed into that browser terminal.

---

## Step 6 — Install Docker

```sh
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2
sudo usermod -aG docker "$USER"
```

Now **close the browser terminal tab and reconnect** (the Connect button
again). The last command only takes effect on a fresh login. Verify:

```sh
docker ps
```

An empty table with headers = success. `permission denied` = you didn't
reconnect.

---

## Step 7 — Let the server download your image

GitHub Container Registry images are private by default, so the server
needs read permission.

**On your laptop:** create a token at
<https://github.com/settings/tokens> → **Generate new token (classic)**.
Name it `formiq-server`, set expiry to 90 days, and tick **only**
`read:packages`. Generate it and copy the `ghp_...` string — GitHub shows
it once.

**Back in the server terminal**, replacing the token:

```sh
echo 'ghp_YOUR_TOKEN_HERE' | docker login ghcr.io -u etctran --password-stdin
```

Expect `Login Succeeded`.

---

## Step 8 — Create the config

Still on the server. This makes the folder your database lives in, a
secret key, and the file describing how to run the container.

```sh
sudo mkdir -p /opt/formiq/data
sudo chown -R "$USER" /opt/formiq
cd /opt/formiq
```

Generate a random password for your API and save it into the config:

```sh
KEY=$(openssl rand -hex 32)
cat > .env <<EOF
IMAGE=ghcr.io/etctran/formiq/backend:latest
FORMIQ_API_KEY=$KEY
EOF
cat .env
```

**Copy the `FORMIQ_API_KEY` value that prints out** — your laptop needs
the identical string in Step 11.

Now the compose file (this mirrors `infra/docker-compose.prod.yml`):

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
database at `/data/formiq.db` inside the container, and the `volumes` line
makes `/data` actually be `/opt/formiq/data` on the SSD. Delete and
recreate the container all you like — the database is outside it.

`restart: unless-stopped` means the container comes back by itself if the
server reboots.

---

## Step 9 — Start it

Check the GitHub Actions run from Step 0 finished green first, then:

```sh
cd /opt/formiq
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

The pull downloads a large image — a few minutes. Then:

```sh
curl -f http://localhost:8000/health
```

Expect `{"status":"ok"}`.

If something's wrong, read the logs — they say why:

```sh
docker compose -f docker-compose.prod.yml logs
```

---

## Step 10 — Check it from your laptop

On **your own machine**, replacing `<YOUR-IP>` and `<YOUR-KEY>`:

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
- **All three hang/time out** → firewall. Step 4, and re-check your IP.
- **#2 returns `200` instead of `401`** → `FORMIQ_API_KEY` didn't reach the
  container. Check `.env`, then `docker compose ... up -d` again.
- **#3 returns `401`** → the key on your laptop doesn't match the server's.
  Re-read it with `cat /opt/formiq/.env`.

---

## Step 11 — Point the frontend at it

On your laptop, create `frontend/.env.local` (gitignored, never committed):

```
VITE_API_BASE_URL=http://<YOUR-IP>:8000
VITE_API_KEY=<YOUR-KEY>
```

Then `npm run dev` from `frontend/` as usual. Uploading a video now sends
it to the server instead of localhost.

---

## Deploying again later

Every push to `main` rebuilds the image automatically. To pick it up:

```sh
cd /opt/formiq
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

A few seconds of downtime. Your database is untouched — it's on the SSD,
not in the container.

---

## Stopping the bill

Lightsail charges for an instance whether or not it's busy. **Stopping an
instance does not stop charges** — only deleting does.

To pause cheaply: Lightsail → instance → **Stop**. You still pay.
To stop paying: **delete the instance**, and delete the static IP from the
Networking tab (an unattached static IP costs money).

Before deleting, save your data:

```sh
# on the server
sudo apt-get install -y sqlite3    # not installed by default
sqlite3 /opt/formiq/data/formiq.db ".backup /tmp/backup.db"
```

then download `/tmp/backup.db` via the Lightsail browser terminal's
download button.

---

## Backups

Not automated. Simplest option is a Lightsail **automatic snapshot**
(instance → Snapshots → enable), which costs a little extra and captures
the whole disk daily.

A snapshot of a live SQLite file can in principle catch it mid-write. For
one user who isn't uploading during the snapshot window this is a
non-issue; if it ever matters, use the `.backup` command above on a cron
and let snapshots capture that file instead.

---

## Why the frontend stays local

Vite bakes `VITE_*` values into the JavaScript bundle at build time. A
publicly served frontend would therefore ship `VITE_API_KEY` in plain text
to anyone who loaded the page, and the API guard would be pointless.
Serving it properly needs real login accounts, a domain and HTTPS — a much
bigger project. Running `npm run dev` locally costs nothing and keeps the
key on your machine.

---

## Glossary

- **Image** — a frozen snapshot of your app and everything it needs to run.
  Built by GitHub Actions, downloaded by the server.
- **Container** — a running copy of an image. Disposable; anything written
  inside it vanishes when it's replaced, which is why the database lives on
  a mounted volume instead.
- **Volume / bind mount** — a folder on the server's real disk made visible
  inside the container. How data survives.
- **GHCR** — GitHub Container Registry, where your built images are stored.
- **Static IP** — an address that stays the same across restarts.
- **`/32`** — in a firewall rule, "exactly this one IP address".
