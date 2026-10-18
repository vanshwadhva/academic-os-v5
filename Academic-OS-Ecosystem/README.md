# Academic OS Ecosystem

This folder contains the student-facing trimester tracker and its supporting web services.

## Structure

- `frontend/`: Firebase-hosted tracker UI, course curriculum, and assets.
- `backend/`: FastAPI application, auth checks, API schemas, and database wiring.
- `integrations/`: Brightspace/Lumen OAuth and progress synchronization.
- `ml/`, `model_artifacts/`, and `data/`: prediction pipeline, model files, and demo data.
- `services/`, `repositories/`, `scheduler/`, `workers/`, and `monitoring/`: supporting application services.
- `deployment/`, `Dockerfile`, and `docker-compose.yml`: container and infrastructure deployment files.
- `docs/`: API, architecture, deployment, and Lumen integration notes. The handbook PDF is under `docs/source-material/`.

## Run locally

From this folder, install the Python dependencies and start the API:

```sh
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000
```

Serve `frontend/` over HTTP during local development. Firebase Hosting is configured in this folder by `firebase.json` and `.firebaserc`; deploy it from here with:

```sh
firebase deploy --only hosting
```

Firestore access rules are in `firestore.rules`; deploy them separately with `firebase deploy --only firestore:rules`. They allow verified BITS accounts to access only their own tracker documents and deny all other client access.

For the Compose setup, copy `deployment/.env.example` to `.env`, replace the placeholder database password, and generate a Fernet key using the command in the example file. Keep the populated `.env` outside GitHub. Then run `docker compose up --build` from this folder. Compose binds Postgres to localhost only and stores encrypted Lumen credentials in a named volume.

## Data and deployment safety

Keep production credentials and local databases out of GitHub. `.gitignore` excludes SQLite files, `.env` files, Lumen credential files, local archives, and deployment caches. Lumen OAuth is disabled until `LUMEN_CREDENTIALS_ENCRYPTION_KEY` is configured; the service encrypts credentials at rest and refuses to save them without that key. Back up the key in a secret manager: without it, saved Lumen credentials cannot be decrypted.

Lumen sync requires the backend environment variables and OAuth app setup described in `docs/DEPLOYMENT.md` and `docs/LMS_INTEGRATION.md`.
