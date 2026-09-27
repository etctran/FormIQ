# Deploying the backend

Design and rationale: `docs/superpowers/specs/2026-09-27-backend-deployment-design.md`.
Backend only — the frontend runs locally against it.

## One-time: the box

Any EC2 / Lightsail instance with a normal (EBS-backed) root volume.
2 vCPU / 4 GB is comfortable; the image is *pulled*, never built here.

```sh
# on the box
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2
sudo usermod -aG docker "$USER"   # re-login after this
sudo mkdir -p /opt/formiq/data    # the database lives here, on the EBS volume
```

Security group / firewall: port 8000 open **only** to your own IP, port 22
for ssh. Nothing else.

Then put the compose file and its `.env` in `/opt/formiq`:

```sh
# /opt/formiq/.env  — never commit this
IMAGE=ghcr.io/<owner>/<repo>/backend:latest
FORMIQ_API_KEY=<a long random string: openssl rand -hex 32>
```

If the GHCR package is private, authenticate the box once:
`echo <a-github-PAT-with-read:packages> | docker login ghcr.io -u <user> --password-stdin`

## Each deploy

CI builds and pushes the image on every push to `main`
(`.github/workflows/deploy.yml`). On the box:

```sh
cd /opt/formiq
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
curl -f http://localhost:8000/health
```

A few seconds of downtime — one user, one container, acceptable.

## Pointing the frontend at it

`frontend/.env.local` (gitignored):

```
VITE_API_BASE_URL=http://<box-ip>:8000
VITE_API_KEY=<the same FORMIQ_API_KEY>
```

Then `npm run dev` as usual. Don't build a public frontend with these set:
Vite inlines them into the bundle, which would publish the key.

## Checks

```sh
curl -f http://<box-ip>:8000/health                          # 200, no key needed
curl -o /dev/null -w '%{http_code}\n' http://<box-ip>:8000/history   # 401
curl -H "X-API-Key: $FORMIQ_API_KEY" http://<box-ip>:8000/history    # 200
```

The database must survive `docker compose down && up` — it's on the bind
mount, not in the container.

## Backups

Not automated. Either EBS snapshots, or on a cron:
`sqlite3 /opt/formiq/data/formiq.db ".backup /opt/formiq/data/backup-$(date +%F).db"`
