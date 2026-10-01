# Placement Likelihood Engine — Synthetic Data Demo

## What this actually is

A full-stack ML systems exercise: synthetic data generation → feature
engineering → XGBoost training → FastAPI serving → Postgres persistence →
Docker deployment. Built to practice the *systems design*, using a
placement-prediction use case as the vehicle.

**What this is not:** a validated predictor of real placement outcomes.
Every correlation between features (study hours, GPA, quiz scores,
communication score, etc.) and the `placed` label is hand-specified in
`data/generate_synthetic_data.py` (see `placement_logit`). The model
recovers *those assumptions*, not reality. AUC ~0.80 on the synthetic
test set reflects "did the pipeline correctly learn the function I
wrote," nothing else.

If you eventually feed this real student outcome data, that changes
everything — see "Path to real data" below.

## Architecture

```
data/generate_synthetic_data.py   -> synthetic_students.csv
ml/features.py                    -> shared feature engineering (train + serve)
ml/train.py                       -> trains XGBoost, writes model_artifacts/
backend/db.py                     -> SQLAlchemy models, Postgres
backend/schemas.py                -> Pydantic request/response contracts
backend/main.py                   -> FastAPI app (/predict, /students, /students/{id}/outcome)
docker-compose.yml                -> postgres + api
```

## Run it

```bash
# 1. generate data + train (do this locally once, before building containers)
pip install -r requirements.txt
python data/generate_synthetic_data.py
python ml/train.py

# 2. bring up the stack
docker compose up --build
```

API docs: http://localhost:8000/docs

## Endpoints

- `POST /predict` — stateless, pass student features, get back probability + risk band + top contributing features. Doesn't touch DB.
- `POST /students` — upsert a student's features, stores the prediction alongside them.
- `GET /students/{student_id}` — fetch stored record.
- `POST /students/{student_id}/outcome?placed=1` — record the REAL outcome once known. This is the hook for retraining on real data later.

## Path to real data (the part that would make this actually useful)

1. Every time you record a real outcome via `/students/{id}/outcome`, you're building a real-labeled dataset row by row.
2. Once you have a few dozen real (features, outcome) pairs — and realistically you need hundreds to thousands across multiple cohorts, not just your own batch — retrain `ml/train.py` against the real table instead of `synthetic_students.csv`.
3. Until then, treat every probability this API returns as "what my synthetic assumptions imply," not a forecast.

## Known limitations / honest gaps

- No SHAP — per-prediction "top factors" use global feature importance, not true per-instance attribution. Fine for a demo, not for a defensible explanation.
- No auth on the API. Don't expose this publicly as-is.
- No retraining pipeline/MLflow — intentionally skipped. Not worth building until there's real data to retrain on (see `THRESHOLDS`-style argument made earlier about the tracker: infra ahead of data is wasted effort).
- `quiz_score_std` as a "consistency" signal is a synthetic-data convenience, not validated against how quiz variance actually relates to placement in reality.
