"""
Admin dashboard API.

Access flow:
Firebase Authentication -> frontend sends ID token -> backend verifies token ->
email must match ADMIN_DASHBOARD_EMAIL -> admin progress response.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.db import get_db
from services.dashboard_service import (
    AdminAccessDenied,
    DashboardService,
    FirebaseIdTokenVerifier,
    FirebaseTokenError,
    assert_admin_claims,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/dashboard", tags=["admin-dashboard"])
_bearer = HTTPBearer(auto_error=False)
_firebase_verifier = FirebaseIdTokenVerifier()
_dashboard_service = DashboardService()


def require_admin_claims(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> Dict[str, Any]:
    """Verify Firebase ID token and enforce the single allowed admin email."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Firebase ID token is required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        claims = _firebase_verifier.verify(credentials.credentials)
        return assert_admin_claims(claims)
    except FirebaseTokenError as exc:
        logger.warning("Admin dashboard token rejected: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Firebase ID token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except AdminAccessDenied as exc:
        logger.warning("Admin dashboard forbidden for email=%s", getattr(exc, "email", None))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="403 Forbidden: this account cannot access the admin dashboard",
        ) from exc


@router.get("/me")
def admin_me(claims: Dict[str, Any] = Depends(require_admin_claims)) -> Dict[str, Any]:
    """Return the verified admin identity."""
    return {
        "uid": claims.get("sub") or claims.get("user_id"),
        "email": claims.get("email"),
        "admin": True,
    }


@router.get("/progress")
def admin_progress(
    claims: Dict[str, Any] = Depends(require_admin_claims),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Return every stored user's progress for the verified admin."""
    payload = _dashboard_service.get_all_user_progress(db)
    payload["viewer"] = {
        "uid": claims.get("sub") or claims.get("user_id"),
        "email": claims.get("email"),
    }
    return payload
