import json
import logging
import os
import secrets
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlsplit
from fastapi.middleware.cors import CORSMiddleware
from cryptography.fernet import Fernet, InvalidToken

import joblib
import pandas as pd
from fastapi import FastAPI, Depends, Header, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

sys.path.append(str(Path(__file__).resolve().parent.parent))
from ml.features import build_features, feature_columns  # noqa: E402
from backend.db import init_db, get_db, StudentRecord, TrackerProgressRecord  # noqa: E402
from backend.schemas import (  # noqa: E402
    StudentFeatures,
    PredictionResponse,
    StoredStudentResponse,
    TrackerProgressBatchUpload,
)
from integrations.sync_manager import (  # noqa: E402
    LumenAuthRequired,
    LumenCredential,
    SyncAlreadyRunning,
    SyncManager,
)
from monitoring.dashboard import router as admin_dashboard_router, require_admin_claims  # noqa: E402
from services.dashboard_service import FirebaseIdTokenVerifier, FirebaseTokenError  # noqa: E402

ARTIFACT_DIR = Path(__file__).resolve().parent.parent / "model_artifacts"
LUMEN_CREDENTIALS_PATH = Path(os.getenv("LUMEN_CREDENTIALS_PATH", ARTIFACT_DIR.parent / ".lumen_credentials.json"))
LUMEN_CREDENTIALS_ENCRYPTION_KEY = os.getenv("LUMEN_CREDENTIALS_ENCRYPTION_KEY", "").strip()
LUMEN_OAUTH_STATE_TTL_SECONDS = 600
_LUMEN_CREDENTIALS_PREFIX = b"ACADEMIC_OS_FERNET_V1\n"
logger = logging.getLogger(__name__)


def _configured_cors_origins() -> list[str]:
    defaults = [
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "https://bits-dsai-tracker.web.app",
        "https://bits-dsai-tracker.firebaseapp.com",
    ]
    extra = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "").split(",") if origin.strip()]
    origins = list(dict.fromkeys(defaults + extra))
    for origin in origins:
        parsed = urlsplit(origin)
        is_local_http = parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}
        if (
            origin in {"*", "null"}
            or parsed.scheme not in {"https", "http"}
            or (parsed.scheme != "https" and not is_local_http)
            or not parsed.hostname
            or parsed.path != ""
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
        ):
            raise RuntimeError("CORS_ORIGINS must contain explicit HTTPS origins (or localhost HTTP origins).")
    return origins

app = FastAPI(
    title="Academic OS DSP-BITS Tracker",
    description=(
        "DSP-BITS Data Stores & Pipeline tracker with Lumen progress, "
        "feature engineering, XGBoost serving, and persistent student records. "
        "Not a validated predictor of real placement outcomes."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_configured_cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-Id", "X-Idempotency-Key"],
)

app.include_router(admin_dashboard_router)

_model = None
_feature_cols = None
_importance = None
_lumen_credentials: Dict[str, LumenCredential] = {}
_lumen_oauth_states: Dict[str, Dict[str, Any]] = {}
_firebase_verifier = FirebaseIdTokenVerifier()


def _frontend_redirect_url() -> str:
    return os.getenv("FRONTEND_URL", "http://localhost:5500/frontend/index.html")


def _lumen_redirect_uri() -> str:
    return os.getenv("LUMEN_REDIRECT_URI", "http://localhost:8000/api/lumen/callback")


class CredentialEncryptionUnavailable(RuntimeError):
    """Raised when the service has no key for protecting saved Lumen tokens."""


def _credential_cipher() -> Fernet:
    if not LUMEN_CREDENTIALS_ENCRYPTION_KEY:
        raise CredentialEncryptionUnavailable("Lumen credential encryption is not configured.")
    try:
        return Fernet(LUMEN_CREDENTIALS_ENCRYPTION_KEY.encode("ascii"))
    except (ValueError, TypeError, UnicodeEncodeError) as exc:
        raise CredentialEncryptionUnavailable("Lumen credential encryption key is invalid.") from exc


def _credential_to_dict(credential: LumenCredential) -> Dict[str, Any]:
    return {
        "access_token": credential.access_token,
        "expires_in": credential.expires_in,
        "lms_user_id": credential.lms_user_id,
        "refresh_token": credential.refresh_token,
        "auth_type": credential.auth_type,
        "issued_at": credential.issued_at,
    }


def _credential_from_dict(payload: Dict[str, Any]) -> LumenCredential:
    return LumenCredential(
        access_token=payload["access_token"],
        expires_in=int(payload.get("expires_in", 3600)),
        lms_user_id=payload.get("lms_user_id"),
        refresh_token=payload.get("refresh_token"),
        auth_type=payload.get("auth_type", "oauth2"),
        issued_at=payload.get("issued_at"),
    )


def _load_lumen_credentials() -> None:
    if not LUMEN_CREDENTIALS_PATH.exists():
        return
    try:
        raw = LUMEN_CREDENTIALS_PATH.read_bytes()
        encrypted = raw.startswith(_LUMEN_CREDENTIALS_PREFIX)
        if encrypted:
            payload_bytes = _credential_cipher().decrypt(raw[len(_LUMEN_CREDENTIALS_PREFIX):])
        else:
            # Migrate legacy local plaintext only when an encryption key is configured.
            try:
                _credential_cipher()
            except CredentialEncryptionUnavailable:
                os.chmod(LUMEN_CREDENTIALS_PATH, 0o600)
                raise
            payload_bytes = raw
        payload = json.loads(payload_bytes)
        if not isinstance(payload, dict):
            raise ValueError("Invalid Lumen credential store format.")
        credentials = {
            student_id: _credential_from_dict(data)
            for student_id, data in payload.items()
            if isinstance(data, dict) and data.get("access_token")
        }
        if not encrypted and credentials:
            _save_lumen_credentials(credentials)
        elif encrypted:
            os.chmod(LUMEN_CREDENTIALS_PATH, 0o600)
        _lumen_credentials.update(credentials)
    except (CredentialEncryptionUnavailable, InvalidToken, OSError, ValueError, TypeError, json.JSONDecodeError):
        logger.error("Lumen credentials were not loaded; configure the encryption key and reconnect Lumen.")


def _save_lumen_credentials(credentials: Optional[Dict[str, LumenCredential]] = None) -> None:
    cipher = _credential_cipher()
    source = credentials if credentials is not None else _lumen_credentials
    payload = json.dumps(
        {student_id: _credential_to_dict(credential) for student_id, credential in source.items()},
        indent=2,
    ).encode("utf-8")
    encrypted = _LUMEN_CREDENTIALS_PREFIX + cipher.encrypt(payload)
    LUMEN_CREDENTIALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_path = tempfile.mkstemp(
        prefix=f".{LUMEN_CREDENTIALS_PATH.name}.",
        dir=str(LUMEN_CREDENTIALS_PATH.parent),
    )
    try:
        os.fchmod(file_descriptor, 0o600)
        with os.fdopen(file_descriptor, "wb") as credentials_file:
            credentials_file.write(encrypted)
        os.replace(temporary_path, LUMEN_CREDENTIALS_PATH)
        os.chmod(LUMEN_CREDENTIALS_PATH, 0o600)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)


def _store_lumen_credential(student_id: str, credential: LumenCredential) -> None:
    updated = dict(_lumen_credentials)
    updated[student_id] = credential
    _save_lumen_credentials(updated)
    _lumen_credentials[student_id] = credential


def _new_lumen_oauth_state(student_id: str) -> str:
    now = time.time()
    expired_states = [
        state for state, value in _lumen_oauth_states.items()
        if now - float(value.get("created_at", 0)) > LUMEN_OAUTH_STATE_TTL_SECONDS
    ]
    for state in expired_states:
        _lumen_oauth_states.pop(state, None)
    user_states = sorted(
        (
            (state, float(value.get("created_at", 0)))
            for state, value in _lumen_oauth_states.items()
            if value.get("student_id") == student_id
        ),
        key=lambda item: item[1],
    )
    for state, _created_at in user_states[:-4]:
        _lumen_oauth_states.pop(state, None)
    if len(_lumen_oauth_states) >= 10000:
        oldest_state = min(
            _lumen_oauth_states,
            key=lambda state: float(_lumen_oauth_states[state].get("created_at", 0)),
        )
        _lumen_oauth_states.pop(oldest_state, None)
    state = secrets.token_urlsafe(32)
    _lumen_oauth_states[state] = {"student_id": student_id, "created_at": now}
    return state


def _require_firebase_user(authorization: Optional[str], expected_student_id: str) -> Dict[str, Any]:
    claims = _require_authenticated_student(authorization)
    if claims["sub"] != expected_student_id:
        raise HTTPException(status_code=403, detail="Firebase user cannot access another student.")
    return claims


def _require_authenticated_student(authorization: Optional[str]) -> Dict[str, Any]:
    """Require a verified BITS Firebase identity for student-owned operations."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Firebase ID token is required.")
    try:
        claims = _firebase_verifier.verify(authorization[7:].strip())
    except FirebaseTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid Firebase ID token.") from exc

    email = str(claims.get("email") or "").strip().lower()
    if (
        not claims.get("sub")
        or not email.endswith("@bitspilani-digital.edu.in")
        or claims.get("email_verified") is not True
    ):
        raise HTTPException(status_code=403, detail="A BITS student account is required.")
    return claims


def _tracker_prediction(completion_pct: float) -> Dict[str, Any]:
    """Mirror the tracker's displayed completion-based guidance for admin reporting."""
    if completion_pct >= 80:
        expected, risk, consistency, study_time = "Excellent", "Low", "Very High", "1.5–2 hrs/day"
    elif completion_pct >= 60:
        expected, risk, consistency, study_time = "Good", "Moderate", "High", "2–3 hrs/day"
    elif completion_pct >= 40:
        expected, risk, consistency, study_time = "Average", "High", "Medium", "3–4 hrs/day"
    else:
        expected, risk, consistency, study_time = "Needs Improvement", "High", "Low", "3–4 hrs/day"

    return {
        "expected_performance": expected,
        "probability_pct": min(98, max(25, completion_pct + 10)),
        "risk": risk,
        "consistency": consistency,
        "recommended_study_time": study_time,
        "type": "completion-based heuristic",
        "top_factors": [
            "Course completion",
            "Weekly consistency",
            "Module completion rate",
            "Pending syllabus",
            "Study momentum",
        ],
    }


@app.on_event("startup")
def startup():
    global _model, _feature_cols, _importance
    init_db()
    _load_lumen_credentials()
    model_path = ARTIFACT_DIR / "placement_model.joblib"
    if model_path.exists():
        _model = joblib.load(model_path)
        with open(ARTIFACT_DIR / "feature_columns.json") as f:
            _feature_cols = json.load(f)
        with open(ARTIFACT_DIR / "feature_importance.json") as f:
            _importance = json.load(f)
    else:
        _model = None


def _risk_band(prob: float) -> str:
    if prob >= 0.66:
        return "High likelihood"
    if prob >= 0.33:
        return "Medium likelihood"
    return "Low likelihood"


def _predict(features: StudentFeatures) -> PredictionResponse:
    if _model is None:
        raise HTTPException(
            status_code=503,
            detail="Model not loaded. Run ml/train.py and mount model_artifacts/ before serving.",
        )
    raw_df = pd.DataFrame([features.dict()])
    X = build_features(raw_df)[feature_columns()]
    prob = float(_model.predict_proba(X)[:, 1][0])

    # crude per-instance explanation: for top-importance features, show
    # this student's value relative to dataset-level importance ranking.
    # (Not SHAP - a real per-instance attribution. Good enough for a demo;
    # swap in SHAP if you need defensible per-prediction explanations.)
    top_factors = []
    for feat, imp in list(_importance.items())[:5]:
        value = float(X[feat].iloc[0]) if feat in X.columns else None
        top_factors.append({"feature": feat, "global_importance": imp, "student_value": value})

    return PredictionResponse(
        student_id=features.student_id,
        placement_probability=round(prob, 4),
        risk_band=_risk_band(prob),
        top_factors=top_factors,
    )


@app.get("/health")
def health():
    return {"status": "ok", "model_loaded": _model is not None}


@app.get("/api/lumen/connect-url")
def lumen_connect_url(
    student_id: str = Query(..., min_length=1, max_length=128),
    authorization: Optional[str] = Header(None),
):
    """
    Create a Brightspace OAuth URL for the student.

    Requires LUMEN_CLIENT_ID/LUMEN_CLIENT_SECRET to be configured and registered
    in the BITS Lumen Brightspace tenant.
    """
    _require_firebase_user(authorization, student_id)
    try:
        _credential_cipher()
    except CredentialEncryptionUnavailable as exc:
        raise HTTPException(status_code=503, detail="Lumen credential encryption is not configured.") from exc
    manager = SyncManager.from_env()
    if not manager.client_id:
        raise HTTPException(
            status_code=503,
            detail="LUMEN_CLIENT_ID is not configured on the backend.",
        )

    state = _new_lumen_oauth_state(student_id)
    auth_url = manager.build_oauth_url(redirect_uri=_lumen_redirect_uri(), state=state)
    return {
        "auth_url": auth_url,
        "state": state,
        "redirect_uri": _lumen_redirect_uri(),
        "base_url": manager.base_url,
    }


@app.get("/api/lumen/callback")
def lumen_callback(
    code: str = Query(..., min_length=1, max_length=2048),
    state: str = Query(..., min_length=16, max_length=256),
):
    state_payload = _lumen_oauth_states.pop(state, None)
    if (
        not state_payload
        or time.time() - float(state_payload.get("created_at", 0)) > LUMEN_OAUTH_STATE_TTL_SECONDS
    ):
        raise HTTPException(status_code=400, detail="Invalid or expired Lumen OAuth state.")

    manager = SyncManager.from_env()
    try:
        credential = manager.exchange_code(code=code, redirect_uri=_lumen_redirect_uri())
    except Exception as exc:
        logger.warning("Lumen OAuth token exchange failed.")
        raise HTTPException(status_code=400, detail="Lumen token exchange failed.") from exc

    student_id = state_payload["student_id"]
    try:
        _store_lumen_credential(student_id, credential)
    except CredentialEncryptionUnavailable as exc:
        raise HTTPException(status_code=503, detail="Lumen credential encryption is not configured.") from exc
    return RedirectResponse(f"{_frontend_redirect_url()}?lumen=connected")


@app.get("/api/lumen/progress")
def lumen_progress(
    student_id: str = Query(..., min_length=1, max_length=128),
    authorization: Optional[str] = Header(None),
):
    """
    Fetch live progress from Lumen and return a dashboard-ready payload.

    The Firebase identity must own student_id. Lumen credentials are loaded
    only from the encrypted server-side credential store.
    """
    _require_firebase_user(authorization, student_id)

    credential = _lumen_credentials.get(student_id)
    manager = SyncManager.from_env()

    if credential and credential.is_expired() and credential.refresh_token:
        try:
            credential = manager.refresh_credential(credential)
            _store_lumen_credential(student_id, credential)
        except CredentialEncryptionUnavailable as exc:
            raise HTTPException(status_code=503, detail="Lumen credential encryption is not configured.") from exc
        except Exception as exc:
            logger.warning("Lumen token refresh failed for an authenticated student.")
            raise HTTPException(status_code=502, detail="Lumen token refresh failed.") from exc

    try:
        payload = manager.fetch_progress(student_id=student_id, credential=credential)
        return payload
    except LumenAuthRequired as exc:
        connect_url = None
        if manager.client_id:
            try:
                _credential_cipher()
                state = _new_lumen_oauth_state(student_id)
                connect_url = manager.build_oauth_url(redirect_uri=_lumen_redirect_uri(), state=state)
            except CredentialEncryptionUnavailable:
                raise HTTPException(
                    status_code=503,
                    detail="Lumen credential encryption is not configured.",
                ) from exc
        raise HTTPException(
            status_code=403,
            detail={
                "reason": exc.reason,
                "message": str(exc),
                "connect_url": connect_url,
            },
        ) from exc
    except SyncAlreadyRunning as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.warning("Lumen progress sync failed for an authenticated student.")
        raise HTTPException(status_code=502, detail="Lumen progress sync failed.") from exc


@app.put("/api/tracker/progress")
def save_tracker_progress(
    batch: TrackerProgressBatchUpload,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """Store the signed-in student's populated trimester snapshots for the admin cohort view."""
    claims = _require_authenticated_student(authorization)
    student_id = claims["sub"]
    email = str(claims.get("email") or "").strip().lower()
    if not batch.snapshots:
        raise HTTPException(status_code=422, detail="At least one populated trimester snapshot is required.")

    trimester_ids = [snapshot.trimester_id for snapshot in batch.snapshots]
    if len(trimester_ids) != len(set(trimester_ids)):
        raise HTTPException(status_code=422, detail="A batch cannot contain duplicate trimester snapshots.")

    updated_snapshots = []
    for snapshot in batch.snapshots:
        courses = [course.model_dump(mode="json") for course in snapshot.courses]
        module_states = [
            module["completed"]
            for course in courses
            for week in course["weeks"]
            for module in week["modules"]
        ]
        total_modules = len(module_states)
        completed_modules = sum(1 for is_complete in module_states if is_complete)
        completion_pct = round((completed_modules / total_modules) * 100, 1) if total_modules else 0.0
        prediction = _tracker_prediction(completion_pct)

        record = db.query(TrackerProgressRecord).filter_by(
            student_id=student_id,
            trimester_id=snapshot.trimester_id,
        ).first()
        prior_lumen_by_course = {}
        if record is not None:
            try:
                prior_courses = json.loads(record.courses_json or "[]")
                prior_lumen_by_course = {
                    course.get("course_id"): course.get("lumen_progress")
                    for course in prior_courses
                    if course.get("course_id") and course.get("lumen_progress")
                }
            except (TypeError, ValueError):
                prior_lumen_by_course = {}
        for course in courses:
            if course.get("lumen_progress") is None:
                course["lumen_progress"] = prior_lumen_by_course.get(course.get("course_id"))

        if record is None:
            record = TrackerProgressRecord(
                student_id=student_id,
                trimester_id=snapshot.trimester_id,
            )
            db.add(record)

        record.student_email = email
        record.trimester_name = snapshot.trimester_name
        record.total_modules = total_modules
        record.completed_modules = completed_modules
        record.completion_pct = completion_pct
        record.courses_json = json.dumps(courses, ensure_ascii=False)
        record.prediction_json = json.dumps(prediction, ensure_ascii=False)
        record.lumen_synced_at = snapshot.lumen_synced_at or record.lumen_synced_at
        updated_snapshots.append({
            "trimester_id": snapshot.trimester_id,
            "completed_modules": completed_modules,
            "total_modules": total_modules,
            "completion_pct": completion_pct,
        })

    db.commit()

    return {
        "student_id": student_id,
        "email": email,
        "snapshots": updated_snapshots,
    }


@app.post("/predict", response_model=PredictionResponse)
def predict(features: StudentFeatures, authorization: Optional[str] = Header(None)):
    """Return the caller's stateless demo prediction."""
    _require_firebase_user(authorization, features.student_id)
    return _predict(features)


@app.post("/students", response_model=StoredStudentResponse)
def create_or_update_student(
    features: StudentFeatures,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """Upsert a student's feature record and store the model's current prediction."""
    _require_firebase_user(authorization, features.student_id)
    prediction = _predict(features)

    existing = db.query(StudentRecord).filter_by(student_id=features.student_id).first()
    payload = features.dict()
    payload["predicted_placement_probability"] = prediction.placement_probability

    if existing:
        for k, v in payload.items():
            setattr(existing, k, v)
        db.commit()
        db.refresh(existing)
        return existing

    record = StudentRecord(**payload)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@app.get("/students/{student_id}", response_model=StoredStudentResponse)
def get_student(
    student_id: str,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    _require_firebase_user(authorization, student_id)
    record = db.query(StudentRecord).filter_by(student_id=student_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Student not found")
    return record


@app.post("/students/{student_id}/outcome")
def record_outcome(
    student_id: str,
    placed: int = Query(..., ge=0, le=1),
    _admin_claims: Dict[str, Any] = Depends(require_admin_claims),
    db: Session = Depends(get_db),
):
    """
    Record the REAL outcome once known (placed 0/1). This is the hook for
    eventually retraining on real labels instead of synthetic ones - the
    whole point of storing predictions alongside ground truth.
    """
    record = db.query(StudentRecord).filter_by(student_id=student_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Student not found")
    record.actual_placed = placed
    db.commit()
    return {"student_id": student_id, "actual_placed": placed}
