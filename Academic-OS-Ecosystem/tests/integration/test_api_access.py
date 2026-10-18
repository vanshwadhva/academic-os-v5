"""
API-level checks: admin-only dashboard, per-student ownership, Lumen progress
persistence, token leakage, and extension CORS. Firebase verification is
replaced with a fake that maps test tokens to claims; everything else is real.
"""

import json

import pytest
from fastapi.testclient import TestClient

from integrations.sync_manager import LumenCredential, SyncManager
from services.dashboard_service import FirebaseIdTokenVerifier

ADMIN_EMAIL = "2025em1300265@bitspilani-digital.edu.in"

CLAIMS = {
    "admin-token": {"sub": "uid-admin", "email": ADMIN_EMAIL, "email_verified": True},
    "admin-unverified": {"sub": "uid-admin", "email": ADMIN_EMAIL, "email_verified": False},
    "student-a-token": {"sub": "uid-student-a", "email": "student.a@bitspilani-digital.edu.in", "email_verified": True},
    "student-b-token": {"sub": "uid-student-b", "email": "student.b@bitspilani-digital.edu.in", "email_verified": True},
    "outsider-token": {"sub": "uid-outsider", "email": "someone@gmail.com", "email_verified": True},
    "lookalike-token": {"sub": "uid-lookalike", "email": "2025em1300265@gmail.com", "email_verified": True},
}


def _fake_verify(self, id_token):
    if id_token not in CLAIMS:
        from services.dashboard_service import FirebaseTokenError
        raise FirebaseTokenError("unknown test token")
    return dict(CLAIMS[id_token])


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def app_module(monkeypatch):
    monkeypatch.setattr(FirebaseIdTokenVerifier, "verify", _fake_verify)
    import backend.main as main

    return main


@pytest.fixture
def client(app_module):
    with TestClient(app_module.app) as test_client:
        yield test_client


def _engaged_payload():
    return {
        "sync_status": "success",
        "last_synced_at": "2026-10-18T10:00:00+00:00",
        "courses": [{
            "course_id": "6606",
            "course_name": "Data Stores & Pipelines",
            "course_code": "DSP-101",
            "modules_total": 4,
            "modules_completed": 3,
            "attendance": {"attendance_pct": 85.0},
            "quizzes": [{"percentage": 80}, {"percentage": 60}],
            "grades": [{"percentage": 75}, {"percentage": 65}],
            "modules": [
                {"topic_id": "1", "visited": True, "last_visited": "2026-10-10T14:05:00+00:00", "total_time_seconds": 3600},
                {"topic_id": "2", "visited": True, "last_visited": "2026-10-11T14:40:00+00:00", "total_time_seconds": 1200},
                {"topic_id": "3", "visited": True, "last_visited": "2026-10-12T08:10:00+00:00", "total_time_seconds": 600},
                {"topic_id": "4", "visited": False},
            ],
        }],
        "domain_errors": {},
        "has_errors": False,
    }


# ---------------------------------------------------------------------------
# Admin dashboard
# ---------------------------------------------------------------------------

def test_admin_dashboard_requires_a_token(client):
    assert client.get("/api/admin/dashboard/progress").status_code == 401


@pytest.mark.parametrize("token", ["student-a-token", "outsider-token", "lookalike-token", "admin-unverified"])
def test_admin_dashboard_rejects_everyone_but_the_verified_admin(client, token):
    response = client.get("/api/admin/dashboard/progress", headers=_auth(token))
    assert response.status_code == 403


def test_admin_dashboard_admits_the_verified_admin(client):
    response = client.get("/api/admin/dashboard/progress", headers=_auth("admin-token"))
    assert response.status_code == 200
    assert response.json()["viewer"]["email"] == ADMIN_EMAIL


def test_admin_dashboard_shows_lumen_profile_and_ml_prediction_for_a_student(client, app_module, monkeypatch):
    monkeypatch.setattr(
        SyncManager, "fetch_progress_with_credential",
        lambda self, student_id, credential: (_engaged_payload(), None),
    )
    app_module._lumen_credentials["uid-student-a"] = LumenCredential(
        access_token="tok", expires_in=3600, issued_at="2026-10-18T09:00:00+00:00",
    )
    assert client.put(
        "/api/students/me/profile",
        headers=_auth("student-a-token"),
        json={"aptitude_score": 72, "trimester_gpa": 8.0},
    ).status_code == 200
    assert client.get("/api/lumen/progress", params={"student_id": "uid-student-a"},
                      headers=_auth("student-a-token")).status_code == 200

    users = client.get("/api/admin/dashboard/progress", headers=_auth("admin-token")).json()["users"]
    user = next(u for u in users if u["student_id"] == "uid-student-a")
    assert user["lumen"]["courses"][0]["course_id"] == "6606"
    assert user["profile"] == {"aptitude_score": 72.0, "trimester_gpa": 8.0}
    assert user["ml_prediction"]["status"] == "ready"
    assert 0 <= user["prediction"]["placement_probability"] <= 1


# ---------------------------------------------------------------------------
# Student ownership
# ---------------------------------------------------------------------------

def test_student_profile_is_private_to_its_owner(client):
    client.put("/api/students/me/profile", headers=_auth("student-b-token"), json={"aptitude_score": 40})
    own = client.get("/api/students/me/profile", headers=_auth("student-a-token")).json()
    assert own["student_id"] == "uid-student-a"
    assert own["profile"].get("aptitude_score") != 40  # B's value must never leak into A's profile


def test_profile_rejects_out_of_range_values(client):
    response = client.put("/api/students/me/profile", headers=_auth("student-a-token"), json={"trimester_gpa": 42})
    assert response.status_code == 422


def test_profile_endpoints_require_a_bits_student_account(client):
    assert client.get("/api/students/me/profile", headers=_auth("outsider-token")).status_code == 403
    assert client.put("/api/students/me/profile", headers=_auth("outsider-token"), json={}).status_code == 403


def test_student_cannot_fetch_another_students_lumen_progress(client):
    response = client.get("/api/lumen/progress", params={"student_id": "uid-student-b"},
                          headers=_auth("student-a-token"))
    assert response.status_code == 403


def test_insights_awaiting_lumen_for_new_student(client):
    body = client.get("/api/students/me/insights", headers=_auth("student-b-token")).json()
    assert body["status"] == "awaiting_lumen"


# ---------------------------------------------------------------------------
# Lumen progress: persistence, token handling, failure handling
# ---------------------------------------------------------------------------

def test_lumen_progress_persists_refreshed_tokens_and_never_returns_them(client, app_module, monkeypatch):
    refreshed = LumenCredential(access_token="NEW-ACCESS-SECRET", expires_in=3600, refresh_token="NEW-REFRESH")
    monkeypatch.setattr(
        SyncManager, "fetch_progress_with_credential",
        lambda self, student_id, credential: (_engaged_payload(), refreshed),
    )
    app_module._lumen_credentials["uid-student-a"] = LumenCredential(
        access_token="OLD", expires_in=3600, issued_at="2026-10-18T09:00:00+00:00",
    )
    response = client.get("/api/lumen/progress", params={"student_id": "uid-student-a"},
                          headers=_auth("student-a-token"))
    assert response.status_code == 200
    assert app_module._lumen_credentials["uid-student-a"].access_token == "NEW-ACCESS-SECRET"
    assert "NEW-ACCESS-SECRET" not in response.text
    assert "NEW-REFRESH" not in response.text

    from backend.db import LumenSyncRecord, SessionLocal

    with SessionLocal() as db:
        stored = db.query(LumenSyncRecord).filter_by(student_id="uid-student-a").one()
        assert "SECRET" not in stored.payload_json and "REFRESH" not in stored.payload_json
        assert "SECRET" not in stored.insights_json


def test_failed_lumen_sync_is_an_error_not_an_empty_dashboard(client, app_module, monkeypatch):
    failed = _engaged_payload()
    failed["sync_status"] = "failed"
    monkeypatch.setattr(
        SyncManager, "fetch_progress_with_credential",
        lambda self, student_id, credential: (failed, None),
    )
    app_module._lumen_credentials["uid-student-a"] = LumenCredential(
        access_token="tok", expires_in=3600, issued_at="2026-10-18T09:00:00+00:00",
    )
    response = client.get("/api/lumen/progress", params={"student_id": "uid-student-a"},
                          headers=_auth("student-a-token"))
    assert response.status_code == 502


def test_lumen_progress_without_a_connection_asks_to_connect(client, app_module):
    app_module._lumen_credentials.pop("uid-student-a", None)
    response = client.get("/api/lumen/progress", params={"student_id": "uid-student-a"},
                          headers=_auth("student-a-token"))
    assert response.status_code == 403
    assert response.json()["detail"]["reason"] == "lms_not_linked"


# ---------------------------------------------------------------------------
# Extension CORS
# ---------------------------------------------------------------------------

VALID_EXTENSION_ID = "abcdefghijklmnopabcdefghijklmnop"


def test_chrome_extension_origin_allowed_only_when_listed(app_module, monkeypatch):
    monkeypatch.setenv("CHROME_EXTENSION_ORIGINS", f"chrome-extension://{VALID_EXTENSION_ID}")
    assert f"chrome-extension://{VALID_EXTENSION_ID}" in app_module._configured_cors_origins()

    monkeypatch.setenv("CHROME_EXTENSION_ORIGINS", "")
    assert not any(o.startswith("chrome-extension://") for o in app_module._configured_cors_origins())


def test_malformed_extension_origin_is_rejected(app_module, monkeypatch):
    monkeypatch.setenv("CHROME_EXTENSION_ORIGINS", "chrome-extension://not-a-real-id")
    with pytest.raises(RuntimeError):
        app_module._configured_cors_origins()


def test_wildcard_origin_is_rejected(app_module, monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "*")
    with pytest.raises(RuntimeError):
        app_module._configured_cors_origins()
    monkeypatch.setenv("CORS_ORIGINS", "")
