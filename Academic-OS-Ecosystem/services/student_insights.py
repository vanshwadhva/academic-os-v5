"""
Turn a student's Lumen activity and self-reported profile into placement-model
inputs, then score them.

Every model input is tagged with where it came from:

* ``lumen``          - derived from the student's own Lumen activity
* ``self_reported``  - entered by the student in the tracker profile form
* ``imputed``        - neither source had it; the training-set median is used

The response reports how many inputs fell into each bucket, so the UI can say
how much of a prediction is behaviour-based. The model is trained on synthetic
data and is not validated on real placement outcomes (see metrics.json).
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from zoneinfo import ZoneInfo

import pandas as pd

from ml.features import RAW_FEATURE_COLUMNS, build_features, feature_columns

ARTIFACT_DIR = Path(__file__).resolve().parent.parent / "model_artifacts"
DISPLAY_TZ = ZoneInfo("Asia/Kolkata")
TRIMESTER_WEEKS = 12
# Activity dates needed before a "study time" or "consistency" value is trusted.
MIN_ACTIVITY_TIMESTAMPS = 3
# Below this many Lumen-derived inputs a prediction is mostly imputed; refuse it.
MIN_LUMEN_INPUTS = 3

SELF_REPORTED_FEATURES = (
    "aptitude_score",
    "communication_score",
    "trimester_gpa",
    "backlogs_count",
    "projects_count",
    "internships_count",
    "mock_interviews_attended",
)

SOURCE_LUMEN = "lumen"
SOURCE_SELF = "self_reported"
SOURCE_IMPUTED = "imputed"

DISCLAIMER = (
    "Estimate from a model trained on synthetic data. It has not been validated "
    "on real placement outcomes and should not be used for real decisions."
)

_defaults_cache: Optional[Dict[str, float]] = None
_metrics_cache: Optional[Dict[str, Any]] = None


def load_feature_defaults() -> Dict[str, float]:
    global _defaults_cache
    if _defaults_cache is None:
        payload = json.loads((ARTIFACT_DIR / "feature_defaults.json").read_text(encoding="utf-8"))
        _defaults_cache = {k: float(v) for k, v in payload["defaults"].items()}
    return _defaults_cache


def load_synthetic_metrics() -> Dict[str, Any]:
    global _metrics_cache
    if _metrics_cache is None:
        path = ARTIFACT_DIR / "metrics.json"
        _metrics_cache = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return _metrics_cache


def _parse_timestamp(raw: Any) -> Optional[datetime]:
    if not raw or not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def derive_lumen_features(payload: Dict[str, Any]) -> Dict[str, float]:
    """Compute model inputs that the student's Lumen activity actually supports.

    Only values with real evidence are returned. A feature Lumen did not
    provide is left out, so it is imputed rather than guessed.
    """
    courses = [c for c in (payload.get("courses") or []) if isinstance(c, dict)]
    modules = [m for c in courses for m in (c.get("modules") or []) if isinstance(m, dict)]
    found: Dict[str, float] = {}

    total_modules = sum(int(c.get("modules_total") or 0) for c in courses)
    completed_modules = sum(int(c.get("modules_completed") or 0) for c in courses)
    if total_modules > 0:
        found["modules_completed_pct"] = round(100.0 * completed_modules / total_modules, 2)

    attendance = [
        c["attendance"]["attendance_pct"]
        for c in courses
        if isinstance(c.get("attendance"), dict) and c["attendance"].get("attendance_pct") is not None
    ]
    if attendance:
        found["attendance_pct"] = round(statistics.fmean(attendance), 2)

    quiz_scores = [
        float(q["percentage"])
        for c in courses
        for q in (c.get("quizzes") or [])
        if isinstance(q, dict) and q.get("percentage") is not None
    ]
    if quiz_scores:
        found["avg_quiz_score"] = round(statistics.fmean(quiz_scores), 2)
        found["quiz_score_std"] = round(statistics.pstdev(quiz_scores), 2) if len(quiz_scores) > 1 else 0.0

    # Brightspace exposes no assignment score field here; graded-item percentages
    # are the closest Lumen measure of graded work. This is a proxy, not a like-for-like match.
    graded = [
        float(g["percentage"])
        for c in courses
        for g in (c.get("grades") or [])
        if isinstance(g, dict) and g.get("percentage") is not None
    ]
    if graded:
        found["assignment_avg"] = round(statistics.fmean(graded), 2)

    content_seconds = sum(int(m.get("total_time_seconds") or 0) for m in modules)
    if content_seconds > 0:
        found["weekly_study_hours"] = round(min(80.0, content_seconds / 3600 / TRIMESTER_WEEKS), 2)

    visits = [ts for ts in (_parse_timestamp(m.get("last_visited")) for m in modules) if ts]
    if len(visits) >= MIN_ACTIVITY_TIMESTAMPS:
        local = [ts.astimezone(DISPLAY_TZ) for ts in visits]
        found["preferred_study_hour"] = Counter(ts.hour for ts in local).most_common(1)[0][0]
        active_days = {ts.date() for ts in local}
        found["consistency_score"] = round(min(1.0, len(active_days) / (TRIMESTER_WEEKS * 7)), 4)

    return found


def build_model_inputs(
    payload: Optional[Dict[str, Any]],
    profile: Optional[Dict[str, Any]],
) -> Tuple[Dict[str, float], Dict[str, str]]:
    """Return (feature values, source tag per feature) for all 15 raw inputs."""
    lumen = derive_lumen_features(payload or {})
    profile = profile or {}
    defaults = load_feature_defaults()

    values: Dict[str, float] = {}
    sources: Dict[str, str] = {}
    for column in RAW_FEATURE_COLUMNS:
        if column in lumen:
            values[column], sources[column] = float(lumen[column]), SOURCE_LUMEN
        elif column in SELF_REPORTED_FEATURES and profile.get(column) is not None:
            values[column], sources[column] = float(profile[column]), SOURCE_SELF
        else:
            values[column], sources[column] = defaults[column], SOURCE_IMPUTED
    return values, sources


def score_features(model: Any, values: Dict[str, float]) -> Tuple[float, Dict[str, float]]:
    """Run the trained model. Returns (placement probability, engineered feature row)."""
    raw_df = pd.DataFrame([{col: values[col] for col in RAW_FEATURE_COLUMNS}])
    matrix = build_features(raw_df)[feature_columns()]
    probability = float(model.predict_proba(matrix)[:, 1][0])
    row = {name: float(matrix[name].iloc[0]) for name in matrix.columns}
    return probability, row


def risk_band(probability: float) -> str:
    if probability >= 0.66:
        return "High likelihood"
    if probability >= 0.33:
        return "Medium likelihood"
    return "Low likelihood"


def build_insights(
    model: Any,
    importance: Optional[Dict[str, float]],
    payload: Optional[Dict[str, Any]],
    profile: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Full prediction record for one student. Never raises for missing data."""
    generated_at = datetime.now(timezone.utc).isoformat()
    base_model = {
        "name": "placement_model (XGBoost)",
        "trained_on": "synthetic data",
        "validated_on_real_outcomes": False,
        "synthetic_test_roc_auc": load_synthetic_metrics().get("roc_auc"),
    }

    if model is None:
        return {
            "status": "model_unavailable",
            "message": "The prediction model is not loaded on the server.",
            "generated_at": generated_at,
            "model": base_model,
            "disclaimer": DISCLAIMER,
        }

    if payload is None:
        return {
            "status": "awaiting_lumen",
            "message": "Connect Lumen to base the prediction on your course activity.",
            "generated_at": generated_at,
            "model": base_model,
            "disclaimer": DISCLAIMER,
        }

    values, sources = build_model_inputs(payload, profile)
    lumen_count = sum(1 for s in sources.values() if s == SOURCE_LUMEN)
    if lumen_count < MIN_LUMEN_INPUTS:
        return {
            "status": "insufficient_lumen_data",
            "message": (
                "Not enough course activity in Lumen yet for a prediction. "
                "It will update as modules, quizzes and grades are recorded."
            ),
            "generated_at": generated_at,
            "model": base_model,
            "coverage": _coverage(sources),
            "disclaimer": DISCLAIMER,
        }

    probability, engineered = score_features(model, values)
    factors = []
    for name, importance_value in list((importance or {}).items())[:5]:
        factors.append({
            "feature": name,
            "global_importance": importance_value,
            "student_value": engineered.get(name, values.get(name)),
            "source": sources.get(name, "derived"),
        })

    return {
        "status": "ready",
        "message": None,
        "generated_at": generated_at,
        "placement_probability": round(probability, 4),
        "risk_band": risk_band(probability),
        "model": base_model,
        "coverage": _coverage(sources),
        "inputs": {name: {"value": values[name], "source": sources[name]} for name in RAW_FEATURE_COLUMNS},
        "top_factors": factors,
        "disclaimer": DISCLAIMER,
    }


def _coverage(sources: Dict[str, str]) -> Dict[str, int]:
    counts = Counter(sources.values())
    return {
        "lumen": counts.get(SOURCE_LUMEN, 0),
        "self_reported": counts.get(SOURCE_SELF, 0),
        "imputed": counts.get(SOURCE_IMPUTED, 0),
        "total": len(RAW_FEATURE_COLUMNS),
    }
