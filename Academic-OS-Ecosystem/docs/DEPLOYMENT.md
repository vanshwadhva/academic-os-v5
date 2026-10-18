# Deployment runbook

Four parts are deployed separately:

| Part | Where | Source |
|---|---|---|
| API (FastAPI + model + Lumen sync) | Docker container on a host with PostgreSQL | `Dockerfile`, `backend/` |
| Database | PostgreSQL 16 | `docker-compose.yml` or a managed service |
| Web tracker and admin dashboard | Firebase Hosting | `frontend/`, `firebase.json` |
| Chrome extension | Zip for distribution, or load unpacked | `scripts/build_extension.py` |

Firestore security rules (`firestore.rules`) are deployed with Firebase.

## 0. Before you start

- [ ] Lumen (Brightspace) app registered with BITS IT. You have the client ID and secret, and the callback URL is registered.
- [ ] Firebase project `bits-dsai-tracker` with Google sign-in enabled, restricted to `bitspilani-digital.edu.in`.
- [ ] Google OAuth client for the extension (see `docs/CHROME_EXTENSION.md`, section 3).
- [ ] A PostgreSQL database, and a backup plan (`scripts/backup_database.py`).
- [ ] A Fernet key for encrypting Lumen tokens. Generate it once and store it in your secret manager. **Losing it means every student must reconnect Lumen.**

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## 1. API: configuration

The API refuses to start with `APP_ENV=production` unless these are valid.
The Dockerfile sets `APP_ENV=production` by default. Every problem is listed
in the startup error.

| Variable | Example | Notes |
|---|---|---|
| `APP_ENV` | `production` | Enables the startup checks |
| `DATABASE_URL` | `postgresql://user:pw@host:5432/placement_db` | Must be PostgreSQL |
| `LUMEN_CLIENT_ID` / `LUMEN_CLIENT_SECRET` | from BITS IT | Secret, never commit |
| `LUMEN_BASE_URL` | `https://lumen.bitspilani-digital.edu.in` | |
| `LUMEN_REDIRECT_URI` | `https://api.example.com/api/lumen/callback` | Must match the registered callback, https |
| `LUMEN_CREDENTIALS_ENCRYPTION_KEY` | Fernet key from step 0 | Secret |
| `LUMEN_CREDENTIALS_PATH` | `/app/runtime/lumen_credentials.json` | Must be on a persistent volume |
| `FRONTEND_URL` | `https://bits-dsai-tracker.web.app/index.html` | Or `chrome-extension://<id>/index.html` |
| `FIREBASE_PROJECT_ID` | `bits-dsai-tracker` | |
| `ADMIN_DASHBOARD_EMAIL` | `2025em1300265@bitspilani-digital.edu.in` | The only account that can see the admin dashboard |
| `CORS_ORIGINS` | `https://bits-dsai-tracker.web.app` | Explicit https origins only; `*` is refused |
| `CHROME_EXTENSION_ORIGINS` | `chrome-extension://<id>` | Only if the extension is used |
| `POSTGRES_PASSWORD` | (compose only) | Secret |

## 2. API: build and run

Option A, Render (the planned host):

1. Push the repository to GitHub. Confirm CI passes.
2. In Render: **New > Blueprint**, select the repository. Render reads `render.yaml`
   and creates the database and the `academic-os-api` web service.
3. Render prompts for every `sync: false` value. Fill in:
   - `LUMEN_CLIENT_ID`, `LUMEN_CLIENT_SECRET` (from BITS IT)
   - `LUMEN_CREDENTIALS_ENCRYPTION_KEY` (generated in step 0)
   - `LUMEN_REDIRECT_URI`: `https://<service-name>.onrender.com/api/lumen/callback`
     (the service URL is known only after the first deploy, so you may need to set this
     and redeploy)
   - `FRONTEND_URL`: `https://bits-dsai-tracker.web.app/index.html`
   - `CHROME_EXTENSION_ORIGINS`: only after the extension ID is known
4. Register the same `LUMEN_REDIRECT_URI` with BITS IT. Lumen rejects any callback
   that isn't registered.
5. Confirm `https://<service-name>.onrender.com/health` returns `"database": "ok"`.
6. Point `frontend/config.js` `API_URL` at `https://<service-name>.onrender.com`,
   then deploy the web tracker (step 4).

Render settings that must match the repository layout:

- **Root Directory:** blank (the repository root).
- **Dockerfile Path:** `./Dockerfile`. The Dockerfile is at the repository root and
  copies `Academic-OS-Ecosystem/` into the image.
- **Docker Build Context:** `.` (the repository root).
- **Blueprint file path:** `Academic-OS-Ecosystem/render.yaml` (Blueprint setup only).

If the build reports `open Dockerfile: no such file or directory`, the Dockerfile
Path or Root Directory is pointing at the wrong place.

Render notes:
- **The current service is on the free plan, which does not support persistent
  disks.** Upgrade it to Starter before adding the disk. Without a disk, the Lumen
  credential file is lost on every restart, and every student has to reconnect Lumen.
  The free plan also spins the service down when idle, which delays requests.
- The service runs one instance (`numInstances: 1`). Keep it that way; see the warning below.
- The 1 GB disk at `/app/runtime` holds the encrypted Lumen credentials. If the
  disk is lost, every student must reconnect Lumen. Keep backups of the
  database and set up disk snapshots if Render offers them on your plan.
- Persistent disks need a paid plan (`starter` in `render.yaml`). The database
  plan `basic-256mb` is also paid.

Option B, Docker Compose on one host:

```bash
cp .env.example .env         # then fill in every value above
docker compose up -d --build
curl -s http://localhost:8000/health
```

Option B, any container platform. Build `docker build -t academic-os-api .`,
set the variables above, mount a persistent volume at `/app/runtime`, and point
the platform health check at `/health`.

**Run exactly one instance.** Lumen OAuth state and the decrypted credential
cache are held in process memory, so a second instance would reject some OAuth
callbacks. Scaling out needs those moved to shared storage first.

### Health

`GET /health` returns:

```json
{ "status": "ok", "database": "ok", "model_loaded": true }
```

`status` is `degraded` when the database is unreachable or the model is missing.

## 3. Database

Tables are created on startup (`init_db`). **There are no migrations yet.** Any
schema change needs a migration tool, such as Alembic, before it is deployed.

Back up before each release:

```bash
python scripts/backup_database.py
```

## 4. Web tracker and admin dashboard

1. Set the production API URL in `frontend/config.js`. The default in the file
   is an old host (`academic-os-api.onrender.com`). Replace it with the API
   from step 2 before deploying.
2. Deploy:

```bash
firebase deploy --only hosting,firestore:rules
```

`firebase.json` excludes `index.backup.html` and sets basic security headers.
A Content-Security-Policy is not set yet. Add one only after testing Firebase
sign-in against it, because a wrong policy blocks login.

## 5. Chrome extension

```bash
python scripts/build_extension.py \
  --api-url https://api.example.com \
  --google-client-id <client-id>.apps.googleusercontent.com \
  --zip
```

This produces `extension/dist/` (load unpacked) and
`extension/academic-os-extension-<version>.zip` (for distribution).
Use the real API URL. The build will not run the CSP check unless it succeeds.

After you know the extension ID, set `CHROME_EXTENSION_ORIGINS` and
`FRONTEND_URL` on the API and restart it. See `docs/CHROME_EXTENSION.md`.

## 6. Staging verification (do this before any student uses it)

- [ ] `/health` returns `database: ok` and `model_loaded: true`.
- [ ] Startup refuses to run when one required variable is removed (try it on a copy).
- [ ] Your admin account opens the admin dashboard. A student account gets 403 there.
- [ ] A student signs in on the web tracker. Their profile saves and the estimate updates.
- [ ] Connect Lumen with a real student. Lectures, quizzes, grades, and assignments show values that match Lumen.
- [ ] Load the extension from the zip. Sign in, open the tracker, and run a sync.
- [ ] Restart the API. Confirm Lumen connections still work (the credential file survived).

## 7. Known gaps

- No schema migrations. See step 3.
- No Content-Security-Policy on the hosted site. See step 4.
- `vercel.json` in the repo routes all traffic to the API. It conflicts with the
  Firebase Hosting setup. Do not deploy to Vercel unless you remove it or
  change it deliberately.
- Lumen endpoints for completion, grades, assignments, quizzes, and attendance
  are not yet verified against your tenant. Check them in staging.
- The prediction model is trained on synthetic data and is not validated
  (see `model_artifacts/metrics.json`).
- The legacy extension in `Academic-OS-Chrome-Etension/` should be retired.
