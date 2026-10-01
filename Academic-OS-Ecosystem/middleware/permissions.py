"""
Permissions Middleware — Role-based access control and resource ownership guards.

Implements the security controls mandated by the PRD:

  "Student can access only own academic data."
  "Admin endpoints protected by role-based access control."
  "Background jobs operate on scoped connection credentials."
  "Access logging enabled."
  "Consent records stored."
  "Sensitive logs masked."

Architecture
------------
Three distinct layers are provided:

1. **Principal** — a lightweight, validated identity object extracted from
   the incoming request.  It carries the Google user ID, resolved role(s),
   consent status, and LMS link status.

2. **Permission checks** — pure functions that accept a ``Principal`` and
   raise ``PermissionDenied`` on failure.  They are composable and easy to
   unit-test in isolation.

3. **FastAPI dependency factories** — ``require_*`` callables that wire the
   permission checks into FastAPI's ``Depends`` system.  Route handlers
   declare what they need; enforcement is automatic.

Role hierarchy
--------------
  student  — read/write their own academic data, trigger own syncs
  ops      — read all student data, view sync logs, trigger admin syncs
  admin    — full access including model retraining and data deletion
  service  — internal service accounts (workers, scheduler)

The role is resolved from the ``X-User-Role`` header in development and
from a verified JWT claim or Firebase ID token in production.  The
resolution strategy is pluggable via ``PrincipalResolver``.

Usage in route handlers
-----------------------
::

    from middleware.permissions import (
        require_authenticated,
        require_role,
        require_own_resource,
        require_lms_linked,
        require_consent,
        Role,
    )

    @router.get("/dashboard/overview")
    async def get_overview(
        principal: Principal = Depends(require_authenticated()),
    ):
        ...

    @router.get("/students/{student_id}/predictions")
    async def get_predictions(
        student_id: str,
        principal: Principal = Depends(require_own_resource("student_id")),
    ):
        ...

    @router.post("/admin/sync-logs")
    async def get_sync_logs(
        principal: Principal = Depends(require_role(Role.ADMIN)),
    ):
        ...
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from typing import Any, Callable, FrozenSet, Optional, Set

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — header names kept in one place so they're easy to rotate
# ---------------------------------------------------------------------------

_HEADER_USER_ID = "X-User-Id"
_HEADER_USER_ROLE = "X-User-Role"
_HEADER_CORRELATION = "X-Correlation-Id"
_BEARER_SCHEME = HTTPBearer(auto_error=False)

# ---------------------------------------------------------------------------
# Role definitions
# ---------------------------------------------------------------------------


class Role(str, Enum):
    """
    Roles understood by Academic OS.

    Values are lowercase strings so they round-trip through JWT claims,
    database columns, and HTTP headers without transformation.
    """

    STUDENT = "student"
    OPS = "ops"
    ADMIN = "admin"
    SERVICE = "service"   # internal workers / scheduler


# Role → set of roles that have at least that level of access.
# Any role listed can satisfy a ``require_role(X)`` check.
_ROLE_HIERARCHY: dict[Role, FrozenSet[Role]] = {
    Role.STUDENT: frozenset({Role.STUDENT, Role.OPS, Role.ADMIN}),
    Role.OPS:     frozenset({Role.OPS, Role.ADMIN}),
    Role.ADMIN:   frozenset({Role.ADMIN}),
    Role.SERVICE: frozenset({Role.SERVICE, Role.ADMIN}),
}

# ---------------------------------------------------------------------------
# Permission names — used in audit logs and deny messages
# ---------------------------------------------------------------------------


class Permission(str, Enum):
    """
    Fine-grained permission tokens.

    Permissions are derived from role + context, not stored per-user,
    keeping the system simple while still covering every PRD access rule.
    """

    # Own data — any authenticated student
    READ_OWN_DASHBOARD = "read:own:dashboard"
    READ_OWN_COURSES = "read:own:courses"
    READ_OWN_GRADES = "read:own:grades"
    READ_OWN_PREDICTIONS = "read:own:predictions"
    READ_OWN_SYNC_STATUS = "read:own:sync_status"
    WRITE_OWN_CONSENT = "write:own:consent"
    TRIGGER_OWN_SYNC = "trigger:own:sync"
    DISCONNECT_OWN_LMS = "write:own:disconnect"

    # Admin / ops — cross-student read
    READ_ALL_STUDENTS = "read:all:students"
    READ_ALL_SYNC_LOGS = "read:all:sync_logs"
    TRIGGER_ADMIN_SYNC = "trigger:admin:sync"

    # Admin only — mutations with broad blast radius
    RETRAIN_MODEL = "admin:model:retrain"
    DELETE_STUDENT_DATA = "admin:student:delete"
    MANAGE_USERS = "admin:users:manage"

    # Service accounts
    RUN_BACKGROUND_JOB = "service:job:run"


# Mapping: role → set of permissions granted
_ROLE_PERMISSIONS: dict[Role, Set[Permission]] = {
    Role.STUDENT: {
        Permission.READ_OWN_DASHBOARD,
        Permission.READ_OWN_COURSES,
        Permission.READ_OWN_GRADES,
        Permission.READ_OWN_PREDICTIONS,
        Permission.READ_OWN_SYNC_STATUS,
        Permission.WRITE_OWN_CONSENT,
        Permission.TRIGGER_OWN_SYNC,
        Permission.DISCONNECT_OWN_LMS,
    },
    Role.OPS: {
        Permission.READ_OWN_DASHBOARD,
        Permission.READ_OWN_COURSES,
        Permission.READ_OWN_GRADES,
        Permission.READ_OWN_PREDICTIONS,
        Permission.READ_OWN_SYNC_STATUS,
        Permission.READ_ALL_STUDENTS,
        Permission.READ_ALL_SYNC_LOGS,
        Permission.TRIGGER_ADMIN_SYNC,
    },
    Role.ADMIN: {p for p in Permission},   # admin has every permission
    Role.SERVICE: {
        Permission.RUN_BACKGROUND_JOB,
        Permission.TRIGGER_ADMIN_SYNC,
        Permission.READ_ALL_STUDENTS,
    },
}


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class PermissionDenied(Exception):
    """
    Raised by permission check functions when access is denied.

    Carries a ``reason`` code so callers can distinguish between
    "not authenticated", "wrong role", "not your data", etc. without
    parsing error messages.
    """

    def __init__(
        self,
        message: str,
        reason: str = "forbidden",
        *,
        log_level: int = logging.WARNING,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.log_level = log_level


class ConsentRequired(PermissionDenied):
    """Raised when an action requires consent that has not been granted."""

    def __init__(self, message: str = "LMS data consent is required") -> None:
        super().__init__(message, reason="consent_required")


class LMSNotLinked(PermissionDenied):
    """Raised when an action requires a live LMS connection."""

    def __init__(self, message: str = "Lumen LMS account is not linked") -> None:
        super().__init__(message, reason="lms_not_linked")


# ---------------------------------------------------------------------------
# Principal — the resolved, validated identity attached to every request
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Principal:
    """
    Validated identity for the current request.

    Constructed by ``PrincipalResolver`` and attached to request state so
    multiple permission checks within one request share the same object
    without re-parsing headers.

    Attributes
    ----------
    user_id:
        Google OAuth user ID (``sub`` claim).  Never empty for authenticated
        principals; ``None`` only on the anonymous sentinel.
    role:
        Resolved role for this request.
    email:
        Email address when available from the token.  May be ``None`` for
        service accounts.
    lms_linked:
        ``True`` if this user has an active, non-expired LMS connection.
    consent_granted:
        ``True`` if the student has accepted the LMS data consent prompt.
    correlation_id:
        Request trace ID for joining audit log entries.
    _permissions:
        Resolved permission set — use ``has_permission()`` rather than
        accessing directly.
    """

    user_id: Optional[str]
    role: Role
    email: Optional[str] = None
    lms_linked: bool = False
    consent_granted: bool = False
    correlation_id: Optional[str] = None
    _permissions: FrozenSet[Permission] = field(
        default_factory=frozenset, compare=False, repr=False
    )

    # ------------------------------------------------------------------
    # Convenience predicates
    # ------------------------------------------------------------------

    def is_authenticated(self) -> bool:
        """Return True if this is a real, identified user."""
        return self.user_id is not None

    def has_role(self, minimum_role: Role) -> bool:
        """
        Return True if this principal satisfies ``minimum_role``.

        Uses the role hierarchy so an admin automatically satisfies a
        student-level check.
        """
        allowed = _ROLE_HIERARCHY.get(minimum_role, frozenset())
        return self.role in allowed

    def has_permission(self, permission: Permission) -> bool:
        """Return True if this principal holds the given permission."""
        return permission in self._permissions

    def owns(self, resource_user_id: str) -> bool:
        """
        Return True if this principal is the owner of a resource.

        Admins and ops staff always pass ownership checks (they may read
        any student's data).
        """
        if self.role in (Role.ADMIN, Role.OPS):
            return True
        return self.user_id == resource_user_id

    def __str__(self) -> str:
        uid = self.user_id or "anonymous"
        return f"Principal(user={uid}, role={self.role.value})"


# Sentinel used when no auth headers are present
_ANONYMOUS = Principal(
    user_id=None,
    role=Role.STUDENT,
    _permissions=frozenset(),
)


# ---------------------------------------------------------------------------
# Principal resolver
# ---------------------------------------------------------------------------


class PrincipalResolver:
    """
    Extract and validate the caller's identity from an HTTP request.

    Resolution order
    ----------------
    1. ``Authorization: Bearer <token>`` — verified against Google's public
       JWKS or Firebase Admin SDK when ``token_verifier`` is configured.
    2. ``X-User-Id`` + ``X-User-Role`` headers — accepted **only** in
       non-production environments (``trust_headers=True``).  Used by the
       test suite and local development without a full auth stack.
    3. Anonymous sentinel — returned when no identity can be resolved.
       Callers that require authentication will immediately reject this.

    ``lms_linked`` and ``consent_granted`` are resolved via lightweight
    callbacks so the resolver stays decoupled from the database layer.

    Args:
        trust_headers:
            If True, accept ``X-User-Id`` / ``X-User-Role`` without token
            verification.  **Never True in production.**
        token_verifier:
            Optional async callable ``(token: str) -> dict`` that returns
            a decoded claims dict.  Raise ``ValueError`` on bad tokens.
        lms_status_fn:
            Optional sync callable ``(user_id: str) -> tuple[bool, bool]``
            returning ``(lms_linked, consent_granted)``.  Called once per
            request when a real user ID is resolved.
    """

    def __init__(
        self,
        trust_headers: bool = False,
        token_verifier: Optional[Callable[[str], dict]] = None,
        lms_status_fn: Optional[Callable[[str], tuple[bool, bool]]] = None,
    ) -> None:
        if trust_headers:
            logger.warning(
                "PrincipalResolver: trust_headers=True — "
                "header-based identity is NOT safe for production."
            )
        self._trust_headers = trust_headers
        self._verify_token = token_verifier
        self._lms_status = lms_status_fn

    def resolve(self, request: Request) -> Principal:
        """
        Resolve the principal for ``request``.

        Args:
            request: The incoming FastAPI ``Request``.

        Returns:
            A ``Principal``.  Never raises; returns anonymous sentinel on
            failure so downstream checks produce consistent 401/403 errors.
        """
        correlation_id = request.headers.get(_HEADER_CORRELATION)

        # --- Strategy 1: Bearer token ---
        bearer = self._extract_bearer(request)
        if bearer:
            try:
                return self._resolve_from_token(bearer, correlation_id)
            except Exception as exc:
                logger.warning(
                    "Token verification failed (cid=%s): %s",
                    correlation_id, exc,
                )
                # Fall through to anonymous — force 401 at permission check

        # --- Strategy 2: Trusted headers (dev/test only) ---
        if self._trust_headers:
            user_id = request.headers.get(_HEADER_USER_ID)
            role_raw = request.headers.get(_HEADER_USER_ROLE, Role.STUDENT.value)
            if user_id:
                return self._build_principal(
                    user_id=user_id,
                    role=self._parse_role(role_raw),
                    email=None,
                    correlation_id=correlation_id,
                )

        return _ANONYMOUS

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_bearer(self, request: Request) -> Optional[str]:
        """Pull the raw bearer token from the Authorization header."""
        auth_header = request.headers.get("Authorization", "")
        if auth_header.lower().startswith("bearer "):
            return auth_header[7:].strip()
        return None

    def _resolve_from_token(
        self,
        token: str,
        correlation_id: Optional[str],
    ) -> Principal:
        """Verify token and build a Principal from its claims."""
        if not self._verify_token:
            # No verifier configured — accept token at face value in
            # development but log loudly.
            logger.warning(
                "No token_verifier configured — accepting unverified token. "
                "Configure a verifier before deploying to production."
            )
            # Minimal decode without signature verification
            claims = _decode_jwt_payload_unsafe(token)
        else:
            claims = self._verify_token(token)

        user_id = claims.get("sub") or claims.get("uid") or claims.get("user_id")
        if not user_id:
            raise ValueError("Token missing 'sub' / 'uid' claim")

        role = self._parse_role(claims.get("role", Role.STUDENT.value))
        email = claims.get("email")

        return self._build_principal(
            user_id=user_id,
            role=role,
            email=email,
            correlation_id=correlation_id,
        )

    def _build_principal(
        self,
        user_id: str,
        role: Role,
        email: Optional[str],
        correlation_id: Optional[str],
    ) -> Principal:
        """Construct a Principal, resolving LMS status if a callback exists."""
        lms_linked = False
        consent_granted = False

        if self._lms_status:
            try:
                lms_linked, consent_granted = self._lms_status(user_id)
            except Exception as exc:
                logger.warning(
                    "lms_status_fn failed for user %s: %s — defaulting to unlinked",
                    user_id, exc,
                )

        permissions = frozenset(_ROLE_PERMISSIONS.get(role, set()))

        return Principal(
            user_id=user_id,
            role=role,
            email=email,
            lms_linked=lms_linked,
            consent_granted=consent_granted,
            correlation_id=correlation_id,
            _permissions=permissions,
        )

    @staticmethod
    def _parse_role(raw: str) -> Role:
        """Parse a role string, defaulting to STUDENT on unknown values."""
        try:
            return Role(raw.lower().strip())
        except ValueError:
            logger.warning("Unknown role value %r — defaulting to student", raw)
            return Role.STUDENT


# ---------------------------------------------------------------------------
# Unsafe JWT payload decoder (no signature verification)
# Used only when no token_verifier is configured (local dev).
# ---------------------------------------------------------------------------


def _decode_jwt_payload_unsafe(token: str) -> dict:
    """
    Decode the payload section of a JWT **without verifying the signature**.

    Only used during local development when no ``token_verifier`` is
    configured.  In production this code path must never execute because
    ``PrincipalResolver`` is constructed with a real verifier.

    Args:
        token: Raw JWT string.

    Returns:
        Decoded payload dict.

    Raises:
        ValueError: If the token format is invalid.
    """
    import base64
    import json

    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Not a valid JWT: expected 3 dot-separated parts")

    # JWT uses base64url without padding — add padding back
    payload_b64 = parts[1]
    padding = 4 - len(payload_b64) % 4
    if padding != 4:
        payload_b64 += "=" * padding

    try:
        decoded = base64.urlsafe_b64decode(payload_b64)
        return json.loads(decoded)
    except Exception as exc:
        raise ValueError(f"Failed to decode JWT payload: {exc}") from exc


# ---------------------------------------------------------------------------
# Pure permission check functions
# ---------------------------------------------------------------------------
# These functions accept a Principal and raise PermissionDenied on failure.
# They are deliberately pure (no I/O) so they can be called from anywhere
# and are trivially unit-testable.


def check_authenticated(principal: Principal) -> None:
    """
    Assert the principal is a real, authenticated user.

    Raises:
        PermissionDenied: With reason 'unauthenticated' if not authenticated.
    """
    if not principal.is_authenticated():
        raise PermissionDenied(
            "Authentication required",
            reason="unauthenticated",
            log_level=logging.INFO,
        )


def check_role(principal: Principal, minimum_role: Role) -> None:
    """
    Assert the principal satisfies ``minimum_role``.

    Args:
        principal:    Resolved caller identity.
        minimum_role: The lowest role that may pass this check.

    Raises:
        PermissionDenied: If the principal's role is insufficient.
    """
    check_authenticated(principal)
    if not principal.has_role(minimum_role):
        logger.warning(
            "Role check failed: %s required %s, has %s",
            principal, minimum_role.value, principal.role.value,
        )
        raise PermissionDenied(
            f"Role '{minimum_role.value}' or higher is required",
            reason="insufficient_role",
        )


def check_permission(principal: Principal, permission: Permission) -> None:
    """
    Assert the principal holds an explicit permission.

    Args:
        principal:  Resolved caller identity.
        permission: The required permission token.

    Raises:
        PermissionDenied: If the permission is not granted.
    """
    check_authenticated(principal)
    if not principal.has_permission(permission):
        logger.warning(
            "Permission check failed: %s missing %s",
            principal, permission.value,
        )
        raise PermissionDenied(
            f"Permission '{permission.value}' is required",
            reason="missing_permission",
        )


def check_own_resource(principal: Principal, resource_user_id: str) -> None:
    """
    Assert the principal owns the requested resource.

    Admins and ops staff bypass this check.

    Args:
        principal:         Resolved caller identity.
        resource_user_id:  The user ID embedded in the resource path.

    Raises:
        PermissionDenied: If the resource belongs to a different user.
    """
    check_authenticated(principal)
    if not principal.owns(resource_user_id):
        logger.warning(
            "Ownership check failed: %s attempted to access resource of user %s",
            principal, resource_user_id,
        )
        raise PermissionDenied(
            "You may only access your own data",
            reason="not_owner",
        )


def check_consent(principal: Principal) -> None:
    """
    Assert the student has granted LMS data consent.

    Args:
        principal: Resolved caller identity.

    Raises:
        ConsentRequired: If consent has not been recorded.
    """
    check_authenticated(principal)
    # Admins and service accounts are exempt from student consent checks
    if principal.role in (Role.ADMIN, Role.OPS, Role.SERVICE):
        return
    if not principal.consent_granted:
        logger.info("Consent check failed for %s", principal)
        raise ConsentRequired()


def check_lms_linked(principal: Principal) -> None:
    """
    Assert the student has an active LMS connection.

    Args:
        principal: Resolved caller identity.

    Raises:
        LMSNotLinked: If the LMS is not linked or the connection is stale.
    """
    check_authenticated(principal)
    # Admins and service accounts are exempt
    if principal.role in (Role.ADMIN, Role.OPS, Role.SERVICE):
        return
    if not principal.lms_linked:
        logger.info("LMS link check failed for %s", principal)
        raise LMSNotLinked()


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------


class AccessAuditLogger:
    """
    Record access control decisions to structured logs.

    Every deny event and every sensitive admin action is emitted as a
    structured dict so a log aggregator (CloudWatch, Datadog, etc.) can
    index and alert on them.

    The logger intentionally masks email addresses to comply with the PRD
    requirement: "Sensitive logs masked."
    """

    _logger = logging.getLogger("academic_os.access_audit")

    @classmethod
    def log_allow(
        cls,
        principal: Principal,
        action: str,
        resource: Optional[str] = None,
    ) -> None:
        """
        Log a permitted access event at DEBUG level.

        Args:
            principal: Caller identity.
            action:    Short description of the action (e.g. 'read_dashboard').
            resource:  Optional resource identifier.
        """
        cls._logger.debug(
            "ACCESS_ALLOW",
            extra=_audit_extra(principal, action, resource, "allow"),
        )

    @classmethod
    def log_deny(
        cls,
        principal: Principal,
        action: str,
        reason: str,
        resource: Optional[str] = None,
    ) -> None:
        """
        Log a denied access event at WARNING level.

        Args:
            principal: Caller identity.
            action:    Short description of the attempted action.
            reason:    Deny reason code from ``PermissionDenied.reason``.
            resource:  Optional resource identifier.
        """
        cls._logger.warning(
            "ACCESS_DENY",
            extra=_audit_extra(principal, action, resource, "deny", reason=reason),
        )

    @classmethod
    def log_consent_event(
        cls,
        principal: Principal,
        event_type: str,   # 'granted' | 'revoked'
    ) -> None:
        """Log a consent lifecycle event — required by PRD §Privacy."""
        cls._logger.info(
            "CONSENT_EVENT",
            extra={
                "user_id": principal.user_id,
                "event": event_type,
                "correlation_id": principal.correlation_id,
                "ts": _ts(),
            },
        )

    @classmethod
    def log_lms_event(
        cls,
        principal: Principal,
        event_type: str,   # 'connect' | 'disconnect' | 'sync' | 'revoke'
    ) -> None:
        """Log an LMS connection lifecycle event — required by PRD §Security."""
        cls._logger.info(
            "LMS_EVENT",
            extra={
                "user_id": principal.user_id,
                "event": event_type,
                "correlation_id": principal.correlation_id,
                "ts": _ts(),
            },
        )


def _audit_extra(
    principal: Principal,
    action: str,
    resource: Optional[str],
    decision: str,
    reason: Optional[str] = None,
) -> dict:
    """Build the structured log extra dict, masking PII."""
    return {
        "user_id": principal.user_id,
        "role": principal.role.value,
        # Mask email — show only domain, never full address
        "email_domain": _mask_email(principal.email),
        "action": action,
        "resource": resource,
        "decision": decision,
        "reason": reason,
        "correlation_id": principal.correlation_id,
        "ts": _ts(),
    }


def _mask_email(email: Optional[str]) -> Optional[str]:
    """Return only the domain part of an email address."""
    if not email or "@" not in email:
        return None
    return "@" + email.split("@", 1)[1]


def _ts() -> str:
    """Current UTC timestamp as ISO string."""
    from datetime import datetime, timezone
    return datetime.now(tz=timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# FastAPI dependency factories
# ---------------------------------------------------------------------------
# These return callables suitable for use with FastAPI's Depends().
# A module-level resolver instance is created at import time; it can be
# replaced in tests or at startup via replace_resolver().

_resolver: PrincipalResolver = PrincipalResolver(trust_headers=True)


def replace_resolver(new_resolver: PrincipalResolver) -> None:
    """
    Swap the module-level resolver.

    Call this during application startup to inject a production-grade
    resolver with a real token verifier and LMS status callback::

        from middleware.permissions import replace_resolver, PrincipalResolver
        replace_resolver(PrincipalResolver(
            trust_headers=False,
            token_verifier=verify_firebase_id_token,
            lms_status_fn=lms_connection_service.get_status,
        ))

    Also useful in tests to inject a stub resolver.
    """
    global _resolver
    _resolver = new_resolver
    logger.info("PrincipalResolver replaced: trust_headers=%s", new_resolver._trust_headers)


def _get_principal(request: Request) -> Principal:
    """FastAPI dependency that resolves the current Principal."""
    return _resolver.resolve(request)


def _http_error(exc: PermissionDenied) -> HTTPException:
    """Convert a PermissionDenied into the right HTTPException status code."""
    if exc.reason == "unauthenticated":
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        )
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))


# ------------------------------------------------------------------
# require_authenticated()
# ------------------------------------------------------------------

def require_authenticated() -> Callable:
    """
    FastAPI dependency: require a real, authenticated user.

    Returns:
        The resolved ``Principal``.

    Raises:
        HTTPException 401: If no valid identity is present.

    Example::

        @router.get("/me")
        async def get_profile(p: Principal = Depends(require_authenticated())):
            return {"user_id": p.user_id}
    """
    def _dep(principal: Principal = Depends(_get_principal)) -> Principal:
        try:
            check_authenticated(principal)
        except PermissionDenied as exc:
            AccessAuditLogger.log_deny(principal, "authenticate", exc.reason)
            raise _http_error(exc)
        AccessAuditLogger.log_allow(principal, "authenticate")
        return principal

    return _dep


# ------------------------------------------------------------------
# require_role(minimum_role)
# ------------------------------------------------------------------

def require_role(minimum_role: Role) -> Callable:
    """
    FastAPI dependency: require at least ``minimum_role``.

    Args:
        minimum_role: Lowest acceptable role.

    Returns:
        The resolved ``Principal``.

    Raises:
        HTTPException 401: If not authenticated.
        HTTPException 403: If role is insufficient.

    Example::

        @router.post("/admin/sync-logs")
        async def sync_logs(p: Principal = Depends(require_role(Role.ADMIN))):
            ...
    """
    def _dep(principal: Principal = Depends(_get_principal)) -> Principal:
        try:
            check_role(principal, minimum_role)
        except PermissionDenied as exc:
            AccessAuditLogger.log_deny(
                principal,
                f"require_role:{minimum_role.value}",
                exc.reason,
            )
            raise _http_error(exc)
        AccessAuditLogger.log_allow(principal, f"require_role:{minimum_role.value}")
        return principal

    return _dep


# ------------------------------------------------------------------
# require_permission(permission)
# ------------------------------------------------------------------

def require_permission(permission: Permission) -> Callable:
    """
    FastAPI dependency: require an explicit permission token.

    Args:
        permission: The required ``Permission`` enum value.

    Returns:
        The resolved ``Principal``.

    Raises:
        HTTPException 401: If not authenticated.
        HTTPException 403: If permission is absent.

    Example::

        @router.post("/api/models/retrain")
        async def retrain(p: Principal = Depends(require_permission(Permission.RETRAIN_MODEL))):
            ...
    """
    def _dep(principal: Principal = Depends(_get_principal)) -> Principal:
        try:
            check_permission(principal, permission)
        except PermissionDenied as exc:
            AccessAuditLogger.log_deny(
                principal,
                f"require_permission:{permission.value}",
                exc.reason,
            )
            raise _http_error(exc)
        AccessAuditLogger.log_allow(principal, f"require_permission:{permission.value}")
        return principal

    return _dep


# ------------------------------------------------------------------
# require_own_resource(path_param)
# ------------------------------------------------------------------

def require_own_resource(path_param: str = "student_id") -> Callable:
    """
    FastAPI dependency: require the caller to own the resource in the URL.

    The dependency reads the path parameter named ``path_param`` from the
    request and asserts it matches the authenticated user's ID.  Admins
    and ops staff pass automatically.

    Args:
        path_param: Name of the URL path parameter holding the owner's
                    user ID.  Defaults to ``'student_id'``.

    Returns:
        The resolved ``Principal``.

    Raises:
        HTTPException 401: If not authenticated.
        HTTPException 403: If the resource belongs to a different user.

    Example::

        @router.get("/students/{student_id}/dashboard")
        async def dashboard(
            student_id: str,
            principal: Principal = Depends(require_own_resource("student_id")),
        ):
            ...
    """
    def _dep(
        request: Request,
        principal: Principal = Depends(_get_principal),
    ) -> Principal:
        resource_user_id = request.path_params.get(path_param, "")
        try:
            check_own_resource(principal, resource_user_id)
        except PermissionDenied as exc:
            AccessAuditLogger.log_deny(
                principal,
                f"require_own_resource:{path_param}",
                exc.reason,
                resource=resource_user_id,
            )
            raise _http_error(exc)
        AccessAuditLogger.log_allow(
            principal,
            f"require_own_resource:{path_param}",
            resource=resource_user_id,
        )
        return principal

    return _dep


# ------------------------------------------------------------------
# require_consent()
# ------------------------------------------------------------------

def require_consent() -> Callable:
    """
    FastAPI dependency: require LMS data consent to have been granted.

    Returns:
        The resolved ``Principal``.

    Raises:
        HTTPException 401: If not authenticated.
        HTTPException 403: If consent has not been recorded.

    Example::

        @router.get("/api/dashboard/overview")
        async def overview(p: Principal = Depends(require_consent())):
            ...
    """
    def _dep(principal: Principal = Depends(_get_principal)) -> Principal:
        try:
            check_authenticated(principal)
            check_consent(principal)
        except PermissionDenied as exc:
            AccessAuditLogger.log_deny(principal, "require_consent", exc.reason)
            raise _http_error(exc)
        return principal

    return _dep


# ------------------------------------------------------------------
# require_lms_linked()
# ------------------------------------------------------------------

def require_lms_linked() -> Callable:
    """
    FastAPI dependency: require the student to have a live LMS connection.

    Returns:
        The resolved ``Principal``.

    Raises:
        HTTPException 401: If not authenticated.
        HTTPException 403: With ``reason='lms_not_linked'`` if not linked.

    Example::

        @router.post("/api/sync/start")
        async def start_sync(p: Principal = Depends(require_lms_linked())):
            ...
    """
    def _dep(principal: Principal = Depends(_get_principal)) -> Principal:
        try:
            check_authenticated(principal)
            check_lms_linked(principal)
        except PermissionDenied as exc:
            AccessAuditLogger.log_deny(principal, "require_lms_linked", exc.reason)
            raise _http_error(exc)
        return principal

    return _dep


# ------------------------------------------------------------------
# require_sync_access() — composite guard for sync endpoints
# ------------------------------------------------------------------

def require_sync_access() -> Callable:
    """
    FastAPI dependency: composite guard for sync trigger endpoints.

    Requires:
    - Authenticated
    - Consent granted
    - LMS linked

    This models the PRD sync pre-conditions exactly:
    "Check connection validity and token freshness" before dispatching.

    Returns:
        The resolved ``Principal``.

    Raises:
        HTTPException 401 / 403: With an appropriate reason code.

    Example::

        @router.post("/api/sync/start")
        async def start_sync(p: Principal = Depends(require_sync_access())):
            ...
    """
    def _dep(principal: Principal = Depends(_get_principal)) -> Principal:
        try:
            check_authenticated(principal)
            check_consent(principal)
            check_lms_linked(principal)
        except PermissionDenied as exc:
            AccessAuditLogger.log_deny(principal, "require_sync_access", exc.reason)
            raise _http_error(exc)
        AccessAuditLogger.log_allow(principal, "require_sync_access")
        return principal

    return _dep


# ---------------------------------------------------------------------------
# Permission decorator (non-FastAPI usage — services, workers, scheduler)
# ---------------------------------------------------------------------------


def permission_required(
    *permissions: Permission,
    allow_roles: Optional[tuple[Role, ...]] = None,
) -> Callable:
    """
    Decorator for service-layer methods that need permission enforcement
    outside of an HTTP request context.

    The decorated function must receive a ``principal`` keyword argument.
    Any missing permission raises ``PermissionDenied`` directly (no HTTP
    translation — that is the caller's responsibility).

    Args:
        *permissions:  One or more permissions, ALL of which must be held.
        allow_roles:   Optional additional role bypass — if the principal
                       holds any of these roles, permission checks are
                       skipped entirely.

    Example::

        class SyncService:
            @permission_required(Permission.TRIGGER_OWN_SYNC)
            def trigger_sync(self, student_id: str, *, principal: Principal):
                ...
    """
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            principal: Optional[Principal] = kwargs.get("principal")
            if principal is None:
                raise PermissionDenied(
                    "permission_required: 'principal' keyword argument is missing",
                    reason="missing_principal",
                    log_level=logging.ERROR,
                )

            # Role bypass
            if allow_roles and principal.role in allow_roles:
                return fn(*args, **kwargs)

            for perm in permissions:
                check_permission(principal, perm)

            return fn(*args, **kwargs)

        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Utility: build a service-account Principal for internal jobs
# ---------------------------------------------------------------------------


def make_service_principal(
    job_name: str,
    correlation_id: Optional[str] = None,
) -> Principal:
    """
    Create a ``Principal`` for a background worker or scheduler job.

    Service principals bypass student-facing consent and LMS-link checks
    but are still subject to role-based restrictions on admin actions.

    Args:
        job_name:        Logical name of the job (used as user_id in logs).
        correlation_id:  Optional trace ID for the job run.

    Returns:
        A ``Principal`` with role ``SERVICE``.

    Example::

        principal = make_service_principal("sync_worker", correlation_id=job_id)
        sync_service.run_sync(student_id=sid, principal=principal)
    """
    return Principal(
        user_id=f"service:{job_name}",
        role=Role.SERVICE,
        email=None,
        lms_linked=True,      # service accounts are not subject to link checks
        consent_granted=True,  # service accounts are not subject to consent checks
        correlation_id=correlation_id,
        _permissions=frozenset(_ROLE_PERMISSIONS.get(Role.SERVICE, set())),
    )


# ---------------------------------------------------------------------------
# __all__ — explicit public surface
# ---------------------------------------------------------------------------

__all__ = [
    # Enums
    "Role",
    "Permission",
    # Principal
    "Principal",
    # Exceptions
    "PermissionDenied",
    "ConsentRequired",
    "LMSNotLinked",
    # Resolver
    "PrincipalResolver",
    "replace_resolver",
    # Pure checks (for service layer)
    "check_authenticated",
    "check_role",
    "check_permission",
    "check_own_resource",
    "check_consent",
    "check_lms_linked",
    # FastAPI dependencies
    "require_authenticated",
    "require_role",
    "require_permission",
    "require_own_resource",
    "require_consent",
    "require_lms_linked",
    "require_sync_access",
    # Decorator
    "permission_required",
    # Helpers
    "make_service_principal",
    "AccessAuditLogger",
]
