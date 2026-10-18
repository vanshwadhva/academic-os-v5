"""Deployment guards: production config validation and the health endpoint."""

import pytest
from fastapi.testclient import TestClient

GOOD_PRODUCTION_ENV = {
    "DATABASE_URL": "postgresql://user:pw@db:5432/placement_db",
    "LUMEN_CLIENT_ID": "id",
    "LUMEN_CLIENT_SECRET": "secret",
    "FIREBASE_PROJECT_ID": "bits-dsai-tracker",
    "ADMIN_DASHBOARD_EMAIL": "2025em1300265@bitspilani-digital.edu.in",
    "LUMEN_REDIRECT_URI": "https://api.example.com/api/lumen/callback",
    "FRONTEND_URL": "https://bits-dsai-tracker.web.app/index.html",
}


@pytest.fixture
def main_module():
    import backend.main as main

    return main


def _set_env(monkeypatch, env):
    for key in GOOD_PRODUCTION_ENV:
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)


def test_good_production_configuration_has_no_problems(main_module, monkeypatch):
    _set_env(monkeypatch, GOOD_PRODUCTION_ENV)
    monkeypatch.setattr(main_module, "LUMEN_CREDENTIALS_ENCRYPTION_KEY", "key")
    assert main_module.production_config_problems() == []


def test_sqlite_is_refused_in_production(main_module, monkeypatch):
    _set_env(monkeypatch, dict(GOOD_PRODUCTION_ENV, DATABASE_URL="sqlite:///./placement.db"))
    monkeypatch.setattr(main_module, "LUMEN_CREDENTIALS_ENCRYPTION_KEY", "key")
    assert any("PostgreSQL" in p for p in main_module.production_config_problems())


def test_every_problem_is_reported_together(main_module, monkeypatch):
    _set_env(monkeypatch, {"DATABASE_URL": "sqlite:///x.db"})
    monkeypatch.setattr(main_module, "LUMEN_CREDENTIALS_ENCRYPTION_KEY", "")
    problems = main_module.production_config_problems()
    assert len(problems) >= 6
    assert any("ENCRYPTION_KEY" in p for p in problems)
    assert any("LUMEN_REDIRECT_URI" in p for p in problems)


def test_http_callback_and_localhost_frontend_are_refused(main_module, monkeypatch):
    _set_env(monkeypatch, dict(GOOD_PRODUCTION_ENV,
                               LUMEN_REDIRECT_URI="http://localhost:8000/api/lumen/callback",
                               FRONTEND_URL="http://localhost:5500"))
    monkeypatch.setattr(main_module, "LUMEN_CREDENTIALS_ENCRYPTION_KEY", "key")
    problems = main_module.production_config_problems()
    assert any("LUMEN_REDIRECT_URI" in p for p in problems)
    assert any("FRONTEND_URL" in p for p in problems)


def test_chrome_extension_frontend_url_is_accepted(main_module, monkeypatch):
    _set_env(monkeypatch, dict(GOOD_PRODUCTION_ENV,
                               FRONTEND_URL="chrome-extension://abcdefghijklmnopabcdefghijklmnop/index.html"))
    monkeypatch.setattr(main_module, "LUMEN_CREDENTIALS_ENCRYPTION_KEY", "key")
    assert main_module.production_config_problems() == []


def test_startup_refuses_to_run_with_invalid_production_config(main_module, monkeypatch):
    _set_env(monkeypatch, {"APP_ENV": "production", "DATABASE_URL": "sqlite:///x.db"})
    with pytest.raises(RuntimeError, match="Refusing to start"):
        main_module.startup()


def test_health_reports_database_and_model(main_module):
    with TestClient(main_module.app) as client:
        body = client.get("/health").json()
    assert body["database"] == "ok"
    assert body["model_loaded"] is True
    assert body["status"] == "ok"
