"""Model-input derivation from Lumen activity, provenance labels, and scoring."""

import json
from pathlib import Path

import joblib
import pytest

from ml.features import RAW_FEATURE_COLUMNS
from services.student_insights import (
    DISCLAIMER,
    SOURCE_IMPUTED,
    SOURCE_LUMEN,
    SOURCE_SELF,
    build_insights,
    build_model_inputs,
    derive_lumen_features,
)

ROOT = Path(__file__).resolve().parent.parent.parent
MODEL = joblib.load(ROOT / "model_artifacts" / "placement_model.joblib")
IMPORTANCE = json.loads((ROOT / "model_artifacts" / "feature_importance.json").read_text())


def _engaged_payload():
    return {
        "last_synced_at": "2026-10-18T10:00:00+00:00",
        "courses": [{
            "course_id": "6606",
            "modules_total": 3,
            "modules_completed": 2,
            "attendance": {"attendance_pct": 80.0},
            "quizzes": [{"percentage": 70}, {"percentage": 50}],
            "grades": [{"percentage": 66}, {"percentage": 74}],
            "modules": [
                {"last_visited": "2026-10-10T14:05:00+00:00", "total_time_seconds": 5400},
                {"last_visited": "2026-10-11T14:40:00+00:00", "total_time_seconds": 1200},
                {"last_visited": "2026-10-12T08:10:00+00:00", "total_time_seconds": 600},
            ],
        }],
    }


def _idle_payload():
    return {
        "courses": [{
            "course_id": "6606",
            "modules_total": 20,
            "modules_completed": 0,
            "quizzes": [{"percentage": 20}],
            "grades": [{"percentage": 25}],
            "modules": [],
        }],
    }


def test_derive_lumen_features_only_returns_supported_values():
    features = derive_lumen_features(_engaged_payload())
    assert features["modules_completed_pct"] == pytest.approx(66.67, abs=0.01)
    assert features["attendance_pct"] == 80.0
    assert features["avg_quiz_score"] == 60.0
    assert features["assignment_avg"] == 70.0
    assert features["preferred_study_hour"] == 19  # 14:05 UTC = 19:35 IST (mode of visits)
    assert features["weekly_study_hours"] == pytest.approx(7200 / 3600 / 12, abs=0.01)  # 2h content over 12 weeks
    # No mock_interviews, aptitude or GPA in Lumen: they must not appear as Lumen values.
    assert "aptitude_score" not in features
    assert "mock_interviews_attended" not in features


def test_no_time_or_visit_data_means_no_fabricated_behaviour_values():
    features = derive_lumen_features(_idle_payload())
    assert "weekly_study_hours" not in features
    assert "consistency_score" not in features
    assert "preferred_study_hour" not in features


def test_inputs_are_labelled_by_source():
    values, sources = build_model_inputs(
        _engaged_payload(), {"aptitude_score": 70, "trimester_gpa": 7.5, "projects_count": None}
    )
    assert set(values) == set(RAW_FEATURE_COLUMNS) == set(sources)
    assert sources["modules_completed_pct"] == SOURCE_LUMEN
    assert sources["aptitude_score"] == SOURCE_SELF
    assert sources["trimester_gpa"] == SOURCE_SELF
    assert sources["projects_count"] == SOURCE_IMPUTED
    assert sources["backlogs_count"] == SOURCE_IMPUTED


def test_profile_cannot_override_a_lumen_derived_input():
    values, sources = build_model_inputs(_engaged_payload(), {"attendance_pct": 5.0})
    assert values["attendance_pct"] == 80.0
    assert sources["attendance_pct"] == SOURCE_LUMEN


def test_ready_prediction_reports_coverage_and_disclaimer():
    insights = build_insights(MODEL, IMPORTANCE, _engaged_payload(), {"aptitude_score": 70})
    assert insights["status"] == "ready"
    assert 0 <= insights["placement_probability"] <= 1
    assert insights["coverage"]["total"] == len(RAW_FEATURE_COLUMNS)
    assert insights["coverage"]["lumen"] + insights["coverage"]["self_reported"] + insights["coverage"]["imputed"] == 15
    assert insights["model"]["validated_on_real_outcomes"] is False
    assert insights["disclaimer"] == DISCLAIMER
    assert len(insights["top_factors"]) == 5


def test_engaged_student_scores_higher_than_idle_student():
    engaged = build_insights(MODEL, IMPORTANCE, _engaged_payload(), {"aptitude_score": 80, "trimester_gpa": 9.0})
    idle = build_insights(MODEL, IMPORTANCE, _idle_payload(), {"aptitude_score": 30, "trimester_gpa": 4.0})
    assert engaged["status"] == idle["status"] == "ready"
    assert engaged["placement_probability"] > idle["placement_probability"]


def test_awaiting_lumen_when_no_payload():
    insights = build_insights(MODEL, IMPORTANCE, None, {})
    assert insights["status"] == "awaiting_lumen"
    assert "placement_probability" not in insights


def test_insufficient_lumen_data_refuses_to_predict():
    payload = {"courses": [{"course_id": "1", "modules_total": 2, "modules_completed": 1}]}
    insights = build_insights(MODEL, IMPORTANCE, payload, {})
    assert insights["status"] == "insufficient_lumen_data"
    assert "placement_probability" not in insights


def test_model_unavailable_is_reported_not_raised():
    insights = build_insights(None, IMPORTANCE, _engaged_payload(), {})
    assert insights["status"] == "model_unavailable"
