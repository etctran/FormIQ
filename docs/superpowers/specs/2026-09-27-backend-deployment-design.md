# Backend deployment: single host, durable disk

Status: design. Supersedes the never-written Fargate/ECS design that
`infra/ecs/backend-task-def.json` was a placeholder for.

## Goal

Get `backend/` running on a public IP so the frontend can be pointed at
something other than `localhost:8000`, with the workout-history SQLite
database surviving restarts and redeploys, and without leaving the API
open to the internet.

## Non-goals

- **Multi-user auth.** FormIQ has one user. Accounts, sessions, JWTs and
  per-user data scoping buy nothing until there is a second user, and
  each one is a schema change plus a frontend login flow. The deployment
  needs "not open to the world", which is a shared secret, not identity.
- **Serving the frontend publicly.** Vite inlines `VITE_*` at build time,
  so a public frontend bundle would contain the API key in plain text and
  the guard would be decorative. The frontend runs locally
  (`npm run dev`) against the deployed backend. This also means no
  domain, no TLS, and no nginx in this scope.
- **Horizontal scale / zero-downtime deploys.** One user, one container.
  A redeploy is a few seconds of downtime.
- **Managed Postgres.** SQLite on a local filesystem is what the history
  module already targets and what its tests cover. Migrating costs a
  schema port for headroom nothing currently needs.

## Why not Fargate

Two reasons the earlier design didn't account for:

1. **Ephemeral disk.** Fargate's local storage dies with the task, so
   `backend/data/formiq.db` needs EFS. SQLite over NFS has real locking
   caveats — safe only at exactly one task with one writer, which also
   rules out rolling deploys. That's an EFS filesystem, mount target and
   access point of extra infrastructure bought in order to make SQLite
   work in the one environment it isn't designed for.
2. **Cost shape.** Ingestion is CPU-bound video decode (OpenCV + LiteRT).
   Fargate is the expensive way to buy sustained vCPU.

A single EC2/Lightsail instance with an EBS root volume gives a durable
local filesystem for free — SQLite on the filesystem it expects — and is
cheaper per vCPU. The whole EFS problem is deleted rather than solved.

## Architecture

```
laptop: npm run dev (localhost:5173)
   |  VITE_API_BASE_URL=http://<box-ip>:8000
   |  VITE_API_KEY=<secret>          .env.local, gitignored
   v
box (EC2/Lightsail, EBS root volume)
   docker compose -f docker-compose.prod.yml up -d
   backend container  :8000
     FORMIQ_DB_PATH=/data/formiq.db
     FORMIQ_API_KEY=<secret>
   bind mount  /opt/formiq/data -> /data   (on the EBS volume)
```

The image is **built in CI and pulled on the box, never built there**:
`uv sync` compiles cv-engine and fetches/compiles LiteRT from source
(10+ min, memory-hungry), which would OOM a small instance.

## Access control

`backend/app/security.py` — one `require_api_key` dependency comparing an
`X-API-Key` header against `FORMIQ_API_KEY` with `secrets.compare_digest`.

- Applied at the **router** level for `/history` (covering the previously
  unauthenticated `DELETE /history/{id}` and every sibling route at once)
  and on `POST /analyze/{exercise}`.
- `GET /health` stays open — the container healthcheck curls it
  unauthenticated.
- **When `FORMIQ_API_KEY` is unset the guard is a no-op**, so local dev
  and the test suite are unchanged. Deployments must set it.

The frontend attaches the header in exactly one place, `apiFetch` in
`frontend/src/api.ts`. The CSV/JSON export was a plain `<a href>`, which a
browser can't attach a header to; it now fetches the response and hands
the browser a blob URL instead.

## Durable storage

`FORMIQ_DB_PATH` overrides `DEFAULT_DB_PATH` in
`backend/app/history/database.py`. Set it to a path inside a bind mount
backed by the EBS volume. Nothing else about the history module changes —
it was already written against a plain filesystem path.

Backups: `sqlite3 /opt/formiq/data/formiq.db ".backup ..."` on a cron, or
lean on EBS snapshots. Not automated in this scope.

## Alembic

Still not wired into the deploy. `init_db()`'s `create_all()` runs at app
startup and is sufficient while the schema is additive and single-user.
The first destructive migration is when `alembic upgrade head` has to
become a deploy step.

## Testing

- `backend/tests/test_security.py` — guard off when unset, `/health` open
  when set, missing/wrong key rejected on `/history`,
  `DELETE /history/{id}` and `/analyze`, correct key accepted.
- Existing suites cover the DB-path change implicitly: they already build
  their own engines via `build_engine(tmp_path / ...)`, so only the
  module-level default is affected.

## Manual steps (not automated, deliberately)

Provisioning the instance, opening ports 22 and 8000 to a trusted IP,
installing Docker, creating `/opt/formiq/data`, and putting the secret in
the box's `.env`. One-time, and cheaper to do by hand than to encode in
Terraform for a single box.
