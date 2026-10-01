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

The root Dockerfile and Compose file also live here, so run `docker compose up --build` from this folder when using the container setup.

## Data and deployment safety

Keep production credentials and local databases out of GitHub. `.gitignore` excludes SQLite files, `.env` files, Lumen credential files, local archives, and deployment caches. The existing `placement.db` remains beside `backend/`, matching the backend's default SQLite path; it is excluded from GitHub and Docker builds.

Lumen sync requires the backend environment variables and OAuth app setup described in `docs/DEPLOYMENT.md` and `docs/LMS_INTEGRATION.md`.
