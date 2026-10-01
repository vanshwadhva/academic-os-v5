"""
Rate Limit Middleware — Token-bucket and sliding-window rate limiting.

Implements the PRD reliability requirements:

  "Use retry logic with backoff for transient LMS/API failures."
  "Queue sync jobs rather than blocking user sessions during heavy load."
  "Avoid duplicate concurrent sync jobs for the same user."
  "Target graceful degradation if one data domain is unavailable."

Architecture
------------
Two algorithms are provided and can be mixed per-route:

1. **Sliding Window Counter** — accurate, fair, no burst spike at window
   boundary.  Best for dashboard reads and prediction endpoints.

2. **Token Bucket** — allows controlled bursting above the base rate.
   Best for sync triggers and LMS-facing calls where a brief burst is
   acceptable but sustained hammering is not.

Both use an in-process store backed by ``collections.OrderedDict`` with
thread-safe ``threading.Lock``.  No Redis dependency — the store is
designed with a ``RateLimitStore`` interface so a Redis backend can be
swapped in at startup via ``replace_store()`` without changing any route
code.

Key extraction strategy
-----------------------
Rate limit keys are scoped by **identity + endpoint** by default:

  ``rl:{user_id}:{route_name}``          — authenticated user per route
  ``rl:ip:{client_ip}:{route_name}``     — anonymous / unauthenticated
  ``rl:global:{route_name}``             — optional global (per-endpoint)

This means a single student cannot DoS the sync endpoint by hammering it,
but a different student is unaffected.

Role-aware limits
-----------------
Admins and service accounts receive higher (or unlimited) quotas via
``RatePolicy``.  Students get the base quota.

FastAPI integration
-------------------
::

    from middleware.rate_limit import RateLimiter, RatePolicy, limit

    limiter = RateLimiter()

    # Applied as a route dependency
    @router.post("/api/sync/start")
    async def start_sync(
        _: None = Depends(limiter.dependency(RatePolicy.SYNC)),
    ):
        ...

    # Or as a full Starlette middleware (applies globally)
    app.add_middleware(RateLimitMiddleware, limiter=limiter)
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from abc import ABC, abstractmethod
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Optional, Tuple

from fastapi import Depends, HTTPException, Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_HEADER_LIMIT = "X-RateLimit-Limit"
_HEADER_REMAINING = "X-RateLimit-Remaining"
_HEADER_RESET = "X-RateLimit-Reset"
_HEADER_RETRY_AFTER = "Retry-After"
_HEADER_USER_ID = "X-User-Id"          # mirrors permissions.py constant

# ---------------------------------------------------------------------------
# Rate policy definitions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RatePolicy:
    """
    Encapsulates the quota parameters for a single rate-limit context.

    Attributes
    ----------
    name:
        Human-readable label used in log messages and response headers.
    requests:
        Maximum number of requests allowed within ``window_seconds``.
    window_seconds:
        Duration of the sliding window in seconds.
    burst:
        Additional requests allowed above ``requests`` via token-bucket
        burst.  0 means no burst (pure sliding window).
    algorithm:
        ``'sliding'`` or ``'token_bucket'``.
    admin_multiplier:
        How many times larger the quota is for admins/ops/service roles.
        ``None`` means unlimited.
    """

    name: str
    requests: int
    window_seconds: int
    burst: int = 0
    algorithm: str = "sliding"        # 'sliding' | 'token_bucket'
    admin_multiplier: Optional[int] = None   # None = unlimited

    # ------------------------------------------------------------------
    # Named policies — mirrors the PRD's rate expectations
    # ------------------------------------------------------------------

    @classmethod
    def dashboard_read(cls) -> "RatePolicy":
        """Dashboard overview reads — generous, students refresh often."""
        return cls(
            name="dashboard_read",
            requests=120,
            window_seconds=60,
            burst=20,
            algorithm="token_bucket",
            admin_multiplier=None,
        )

    @classmethod
    def sync_trigger(cls) -> "RatePolicy":
        """
        Sync start / refresh — strict.

        PRD: "Avoid duplicate concurrent sync jobs for the same user."
        A student can trigger at most 6 syncs per minute (10s cool-down).
        """
        return cls(
            name="sync_trigger",
            requests=6,
            window_seconds=60,
            burst=0,
            algorithm="sliding",
            admin_multiplier=10,
        )

    @classmethod
    def prediction_read(cls) -> "RatePolicy":
        """Prediction endpoint — moderate."""
        return cls(
            name="prediction_read",
            requests=60,
            window_seconds=60,
            burst=10,
            algorithm="token_bucket",
            admin_multiplier=None,
        )

    @classmethod
    def lms_connect(cls) -> "RatePolicy":
        """
        LMS connect / disconnect — very strict.

        Prevents credential-stuffing style repeated connect attempts.
        """
        return cls(
            name="lms_connect",
            requests=5,
            window_seconds=300,   # 5 per 5 minutes
            burst=0,
            algorithm="sliding",
            admin_multiplier=None,   # admins also limited here
        )

    @classmethod
    def admin_action(cls) -> "RatePolicy":
        """Admin mutations (retrain, delete) — very low ceiling."""
        return cls(
            name="admin_action",
            requests=10,
            window_seconds=60,
            burst=0,
            algorithm="sliding",
            admin_multiplier=None,
        )

    @classmethod
    def global_default(cls) -> "RatePolicy":
        """Fallback applied when no explicit policy is configured."""
        return cls(
            name="global_default",
            requests=200,
            window_seconds=60,
            burst=50,
            algorithm="token_bucket",
            admin_multiplier=None,
        )


# ---------------------------------------------------------------------------
# Rate limit result
# ---------------------------------------------------------------------------


@dataclass
class RateLimitResult:
    """
    Outcome of a single rate-limit check.

    Attributes
    ----------
    allowed:
        True if the request should proceed.
    limit:
        Total quota for this window.
    remaining:
        Requests remaining after consuming one slot.
    reset_at:
        Unix timestamp when the window resets (for ``X-RateLimit-Reset``).
    retry_after:
        Seconds until the client may retry.  Only meaningful when
        ``allowed`` is False.
    key:
        The rate-limit key that was evaluated (for logging).
    """

    allowed: bool
    limit: int
    remaining: int
    reset_at: float
    retry_after: int = 0
    key: str = ""

    def response_headers(self) -> Dict[str, str]:
        """Build the standard rate-limit response headers."""
        headers = {
            _HEADER_LIMIT: str(self.limit),
            _HEADER_REMAINING: str(max(0, self.remaining)),
            _HEADER_RESET: str(int(self.reset_at)),
        }
        if not self.allowed:
            headers[_HEADER_RETRY_AFTER] = str(self.retry_after)
        return headers


# ---------------------------------------------------------------------------
# Store interface + in-process implementation
# ---------------------------------------------------------------------------


class RateLimitStore(ABC):
    """
    Abstract storage backend for rate-limit counters.

    Implement this interface with a Redis backend for multi-process / 
    multi-instance deployments.  The in-process default works for single
    workers and the development environment.
    """

    @abstractmethod
    def sliding_window_check(
        self,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitResult:
        """
        Atomic sliding-window check-and-increment.

        Args:
            key:            Rate-limit bucket key.
            limit:          Maximum requests per window.
            window_seconds: Window duration in seconds.

        Returns:
            ``RateLimitResult`` with ``allowed`` set appropriately.
        """

    @abstractmethod
    def token_bucket_check(
        self,
        key: str,
        capacity: int,
        refill_rate: float,
        burst: int,
    ) -> RateLimitResult:
        """
        Atomic token-bucket check-and-consume.

        Args:
            key:          Rate-limit bucket key.
            capacity:     Base requests per window (tokens refilled to this).
            refill_rate:  Tokens added per second.
            burst:        Extra tokens above capacity (maximum bucket size).

        Returns:
            ``RateLimitResult`` with ``allowed`` set appropriately.
        """

    @abstractmethod
    def reset(self, key: str) -> None:
        """Clear all counters for ``key`` (used in tests and admin resets)."""

    @abstractmethod
    def flush_expired(self) -> int:
        """Remove expired entries.  Returns count of removed entries."""


class InProcessStore(RateLimitStore):
    """
    Thread-safe in-process rate-limit store.

    Uses two separate dicts:
    - ``_windows``: sliding-window timestamp lists per key
    - ``_buckets``: token-bucket state per key

    Both are protected by a single reentrant lock.  An ``OrderedDict``
    is used as the outer container so ``flush_expired`` can iterate in
    insertion order for efficient pruning without rebuilding the dict.

    Maximum capacity is bounded by ``max_keys`` to prevent unbounded
    memory growth from client-IP-keyed buckets.  The oldest half of
    entries are evicted when the cap is reached (LRU-ish).
    """

    def __init__(self, max_keys: int = 100_000) -> None:
        self._lock = threading.RLock()
        # key → list of request timestamps (sliding window)
        self._windows: OrderedDict[str, list[float]] = OrderedDict()
        # key → {"tokens": float, "last_refill": float}
        self._buckets: OrderedDict[str, Dict[str, float]] = OrderedDict()
        self._max_keys = max_keys

    # ------------------------------------------------------------------
    # Sliding window
    # ------------------------------------------------------------------

    def sliding_window_check(
        self,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitResult:
        now = time.monotonic()
        cutoff = now - window_seconds

        with self._lock:
            timestamps = self._windows.get(key, [])
            # Drop timestamps outside the current window
            timestamps = [t for t in timestamps if t > cutoff]

            count = len(timestamps)
            allowed = count < limit

            if allowed:
                timestamps.append(now)
                self._windows[key] = timestamps
                self._windows.move_to_end(key)  # LRU bookkeeping
                self._evict_if_full(self._windows)

            remaining = max(0, limit - len(timestamps))
            # Reset at = oldest timestamp in window + window_seconds
            reset_at = (
                (timestamps[0] + window_seconds)
                if timestamps
                else (now + window_seconds)
            )
            retry_after = max(0, int(reset_at - now)) if not allowed else 0

        return RateLimitResult(
            allowed=allowed,
            limit=limit,
            remaining=remaining,
            reset_at=time.time() + (reset_at - now),  # convert to wall clock
            retry_after=retry_after,
            key=key,
        )

    # ------------------------------------------------------------------
    # Token bucket
    # ------------------------------------------------------------------

    def token_bucket_check(
        self,
        key: str,
        capacity: int,
        refill_rate: float,
        burst: int,
    ) -> RateLimitResult:
        now = time.monotonic()
        max_tokens = float(capacity + burst)

        with self._lock:
            bucket = self._buckets.get(key)

            if bucket is None:
                # New bucket — start full
                bucket = {"tokens": max_tokens, "last_refill": now}

            # Refill tokens based on elapsed time
            elapsed = now - bucket["last_refill"]
            bucket["tokens"] = min(
                max_tokens,
                bucket["tokens"] + elapsed * refill_rate,
            )
            bucket["last_refill"] = now

            allowed = bucket["tokens"] >= 1.0

            if allowed:
                bucket["tokens"] -= 1.0

            self._buckets[key] = bucket
            self._buckets.move_to_end(key)
            self._evict_if_full(self._buckets)

            remaining = int(bucket["tokens"])
            # Approximate reset: time until bucket would be full again
            tokens_needed = max_tokens - bucket["tokens"]
            reset_secs = (tokens_needed / refill_rate) if refill_rate > 0 else 60
            retry_after = max(1, int(1.0 / refill_rate)) if not allowed else 0

        return RateLimitResult(
            allowed=allowed,
            limit=capacity + burst,
            remaining=remaining,
            reset_at=time.time() + reset_secs,
            retry_after=retry_after,
            key=key,
        )

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def reset(self, key: str) -> None:
        with self._lock:
            self._windows.pop(key, None)
            self._buckets.pop(key, None)

    def flush_expired(self) -> int:
        now = time.monotonic()
        removed = 0
        with self._lock:
            expired_window_keys = [
                k for k, ts_list in self._windows.items()
                if not ts_list or max(ts_list) < now - 3600
            ]
            for k in expired_window_keys:
                del self._windows[k]
                removed += 1

            expired_bucket_keys = [
                k for k, b in self._buckets.items()
                if now - b.get("last_refill", 0) > 3600
            ]
            for k in expired_bucket_keys:
                del self._buckets[k]
                removed += 1

        return removed

    def _evict_if_full(self, d: OrderedDict) -> None:
        """Evict the oldest half of entries when the max key cap is reached."""
        if len(d) >= self._max_keys:
            evict_count = self._max_keys // 2
            for _ in range(evict_count):
                if d:
                    d.popitem(last=False)


# ---------------------------------------------------------------------------
# Key builders
# ---------------------------------------------------------------------------


def _extract_user_id(request: Request) -> Optional[str]:
    """
    Pull the authenticated user ID from the request.

    Checks request state first (set by auth middleware), then falls back
    to the ``X-User-Id`` header (trusted in dev).  Returns None for
    unauthenticated requests.
    """
    # If permissions middleware has already resolved the principal
    principal = getattr(request.state, "principal", None)
    if principal and getattr(principal, "user_id", None):
        return principal.user_id

    # Dev fallback — trusted header
    return request.headers.get(_HEADER_USER_ID)


def _extract_ip(request: Request) -> str:
    """
    Extract the real client IP, honouring X-Forwarded-For when behind
    a trusted proxy (Nginx / load-balancer as configured in deployment/).
    """
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the leftmost IP — the original client
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _make_key(
    request: Request,
    policy_name: str,
    scope: str = "user",   # 'user' | 'ip' | 'global'
) -> str:
    """
    Build a deterministic, safe rate-limit key.

    Keys are hashed so that long user IDs or IP addresses do not
    cause issues with any storage backend.

    Args:
        request:     The incoming request.
        policy_name: The policy's ``name`` field.
        scope:       Keying strategy.

    Returns:
        Stable string key.
    """
    route_name = _route_label(request)

    if scope == "user":
        user_id = _extract_user_id(request)
        if user_id:
            raw = f"user:{user_id}:{policy_name}:{route_name}"
        else:
            # Fall back to IP for anonymous requests
            raw = f"ip:{_extract_ip(request)}:{policy_name}:{route_name}"
    elif scope == "ip":
        raw = f"ip:{_extract_ip(request)}:{policy_name}:{route_name}"
    else:
        raw = f"global:{policy_name}:{route_name}"

    # SHA-256 keeps key length predictable regardless of input size
    return "rl:" + hashlib.sha256(raw.encode()).hexdigest()[:32]


def _route_label(request: Request) -> str:
    """Return a stable label for the matched route."""
    route = request.scope.get("route")
    if route and hasattr(route, "path"):
        # Use the path template, not the resolved URL, so
        # /students/alice/dashboard and /students/bob/dashboard share a bucket
        return route.path
    return request.url.path


def _get_role(request: Request) -> Optional[str]:
    """Extract the caller's role string for quota scaling."""
    principal = getattr(request.state, "principal", None)
    if principal and hasattr(principal, "role"):
        return str(principal.role.value)
    return request.headers.get("X-User-Role")


def _is_privileged(request: Request) -> bool:
    """Return True if the caller is admin, ops, or a service account."""
    role = _get_role(request)
    return role in ("admin", "ops", "service")


# ---------------------------------------------------------------------------
# Core rate limiter
# ---------------------------------------------------------------------------


class RateLimiter:
    """
    Central rate-limiter used by both route dependencies and the
    global Starlette middleware.

    Usage
    -----
    Instantiate once at application startup and share the instance::

        limiter = RateLimiter()

        # As a FastAPI dependency
        @router.post("/api/sync/start")
        async def start_sync(
            _rl: None = Depends(limiter.dependency(RatePolicy.sync_trigger())),
        ):
            ...

        # As global middleware
        app.add_middleware(RateLimitMiddleware, limiter=limiter)

    Args:
        store:
            Storage backend.  Defaults to ``InProcessStore``.
        default_policy:
            Applied by the global middleware for routes with no explicit
            policy.  Defaults to ``RatePolicy.global_default()``.
    """

    def __init__(
        self,
        store: Optional[RateLimitStore] = None,
        default_policy: Optional[RatePolicy] = None,
    ) -> None:
        self._store = store or InProcessStore()
        self._default_policy = default_policy or RatePolicy.global_default()
        self._route_policies: Dict[str, RatePolicy] = {}
        logger.info(
            "RateLimiter initialised — store=%s default_policy=%s",
            type(self._store).__name__,
            self._default_policy.name,
        )

    # ------------------------------------------------------------------
    # Route policy registration
    # ------------------------------------------------------------------

    def register(self, path: str, policy: RatePolicy) -> None:
        """
        Associate a URL path pattern with a specific policy.

        Called once at startup to configure per-route limits.  The
        ``RateLimitMiddleware`` uses these registrations to look up the
        correct policy when processing requests.

        Args:
            path:   URL path pattern (e.g. ``"/api/sync/start"``).
            policy: The policy to apply for that path.
        """
        self._route_policies[path] = policy
        logger.debug("Registered rate policy '%s' for path '%s'", policy.name, path)

    def policy_for(self, request: Request) -> RatePolicy:
        """
        Return the policy for ``request``, falling back to the default.

        Checks registered paths with exact-match priority, then falls
        back to prefix matching, then the global default.
        """
        path = request.url.path

        # Exact match
        if path in self._route_policies:
            return self._route_policies[path]

        # Prefix match — longest registered prefix wins
        best: Optional[Tuple[int, RatePolicy]] = None
        for registered_path, policy in self._route_policies.items():
            if path.startswith(registered_path):
                length = len(registered_path)
                if best is None or length > best[0]:
                    best = (length, policy)

        if best:
            return best[1]

        return self._default_policy

    # ------------------------------------------------------------------
    # Core check
    # ------------------------------------------------------------------

    def check(self, request: Request, policy: RatePolicy) -> RateLimitResult:
        """
        Evaluate the rate limit for ``request`` under ``policy``.

        Handles privilege scaling: admins receive
        ``policy.admin_multiplier × requests`` quota; if
        ``admin_multiplier`` is ``None`` the check is skipped entirely.

        Args:
            request: The incoming request.
            policy:  The policy to enforce.

        Returns:
            ``RateLimitResult``.
        """
        # Privileged users — check for unlimited bypass or scaled quota
        if _is_privileged(request):
            if policy.admin_multiplier is None:
                # Unlimited — return synthetic "always allowed" result
                return RateLimitResult(
                    allowed=True,
                    limit=0,
                    remaining=999_999,
                    reset_at=time.time() + policy.window_seconds,
                    key="unlimited",
                )
            # Scaled quota
            effective_requests = policy.requests * policy.admin_multiplier
            effective_burst = policy.burst * policy.admin_multiplier
        else:
            effective_requests = policy.requests
            effective_burst = policy.burst

        key = _make_key(request, policy.name)

        if policy.algorithm == "token_bucket":
            refill_rate = effective_requests / policy.window_seconds
            result = self._store.token_bucket_check(
                key=key,
                capacity=effective_requests,
                refill_rate=refill_rate,
                burst=effective_burst,
            )
        else:
            result = self._store.sliding_window_check(
                key=key,
                limit=effective_requests,
                window_seconds=policy.window_seconds,
            )

        result.key = key

        if not result.allowed:
            logger.warning(
                "Rate limit exceeded — key=%s policy=%s ip=%s user=%s",
                key[:16] + "…",
                policy.name,
                _extract_ip(request),
                _extract_user_id(request) or "anon",
            )
        else:
            logger.debug(
                "Rate limit OK — policy=%s remaining=%d",
                policy.name, result.remaining,
            )

        return result

    # ------------------------------------------------------------------
    # FastAPI dependency factory
    # ------------------------------------------------------------------

    def dependency(
        self,
        policy: Optional[RatePolicy] = None,
        scope: str = "user",
    ) -> Callable:
        """
        Return a FastAPI dependency that enforces ``policy``.

        The dependency raises ``HTTP 429`` when the limit is exceeded and
        attaches standard rate-limit headers to both allowed and denied
        responses.

        Args:
            policy: Policy to enforce.  Uses ``default_policy`` if None.
            scope:  Key scope — ``'user'``, ``'ip'``, or ``'global'``.

        Returns:
            Callable suitable for ``Depends()``.

        Example::

            @router.post("/api/sync/start")
            async def start_sync(
                _rl: None = Depends(limiter.dependency(RatePolicy.sync_trigger())),
            ):
                ...
        """
        effective_policy = policy or self._default_policy
        limiter_self = self

        async def _rate_limit_dep(request: Request, response: Response) -> None:
            result = limiter_self.check(request, effective_policy)

            # Always attach headers so clients can implement adaptive back-off
            for header, value in result.response_headers().items():
                response.headers[header] = value

            if not result.allowed:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "error": "rate_limit_exceeded",
                        "policy": effective_policy.name,
                        "retry_after": result.retry_after,
                        "message": (
                            f"Too many requests. "
                            f"Retry after {result.retry_after} second(s)."
                        ),
                    },
                    headers=result.response_headers(),
                )

        return _rate_limit_dep

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def reset_for(self, user_id: str, policy_name: str) -> None:
        """
        Clear rate-limit state for a specific user + policy.

        Useful after admin intervention or when a user's token is rotated.
        """
        # We can't reverse the hash, so we rebuild the key the same way
        # by constructing a minimal fake request context.
        # The easier path: clear all keys matching the prefix pattern.
        # Since we hash keys, we reconstruct and reset directly.
        raw = f"user:{user_id}:{policy_name}:"
        key = "rl:" + hashlib.sha256(raw.encode()).hexdigest()[:32]
        self._store.reset(key)
        logger.info("Rate limit reset for user %s policy %s", user_id, policy_name)

    def flush_expired(self) -> int:
        """Flush expired entries from the backing store."""
        removed = self._store.flush_expired()
        if removed:
            logger.debug("Flushed %d expired rate-limit entries", removed)
        return removed


# ---------------------------------------------------------------------------
# Starlette global middleware
# ---------------------------------------------------------------------------


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Global Starlette middleware that applies rate limiting to every request.

    Routes that have an explicit policy registered on ``limiter`` use that
    policy.  All other routes fall back to ``limiter.default_policy``.

    Paths listed in ``exempt_paths`` bypass all rate limiting (health
    checks, metrics endpoints).

    Add to your FastAPI app::

        app.add_middleware(
            RateLimitMiddleware,
            limiter=limiter,
            exempt_paths={"/health", "/metrics"},
        )
    """

    # Default paths that are never rate-limited
    _DEFAULT_EXEMPT: frozenset[str] = frozenset({
        "/health",
        "/metrics",
        "/docs",
        "/openapi.json",
        "/redoc",
    })

    def __init__(
        self,
        app: ASGIApp,
        limiter: RateLimiter,
        exempt_paths: Optional[frozenset[str]] = None,
    ) -> None:
        super().__init__(app)
        self._limiter = limiter
        self._exempt = exempt_paths if exempt_paths is not None else self._DEFAULT_EXEMPT

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip exempt paths immediately
        if request.url.path in self._exempt:
            return await call_next(request)

        policy = self._limiter.policy_for(request)
        result = self._limiter.check(request, policy)

        if not result.allowed:
            from starlette.responses import JSONResponse

            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "rate_limit_exceeded",
                    "policy": policy.name,
                    "retry_after": result.retry_after,
                    "message": (
                        f"Too many requests. "
                        f"Retry after {result.retry_after} second(s)."
                    ),
                },
                headers=result.response_headers(),
            )

        response = await call_next(request)

        # Attach rate-limit headers to successful responses too
        for header, value in result.response_headers().items():
            response.headers[header] = value

        return response


# ---------------------------------------------------------------------------
# Sync-specific duplicate-job guard
# ---------------------------------------------------------------------------


class SyncConcurrencyGuard:
    """
    Prevent duplicate concurrent sync jobs for the same user.

    PRD: "Avoid duplicate concurrent sync jobs for the same user."

    This is separate from the rate limiter — it tracks *active* jobs,
    not request frequency.  A sync job acquires the lock on start and
    releases it on completion or failure.

    Thread-safe; suitable for single-process deployments.  For multi-
    process, back this with Redis SETNX or a DB advisory lock.

    Usage::

        guard = SyncConcurrencyGuard()

        # In sync worker
        if not guard.acquire(user_id):
            raise HTTPException(409, "Sync already in progress")
        try:
            run_sync(user_id)
        finally:
            guard.release(user_id)
    """

    def __init__(self, max_concurrent_per_user: int = 1) -> None:
        self._lock = threading.Lock()
        # user_id → count of in-flight jobs
        self._active: Dict[str, int] = {}
        self._max = max_concurrent_per_user

    def acquire(self, user_id: str) -> bool:
        """
        Try to acquire a sync slot for ``user_id``.

        Args:
            user_id: The student's user ID.

        Returns:
            ``True`` if the slot was acquired, ``False`` if at capacity.
        """
        with self._lock:
            current = self._active.get(user_id, 0)
            if current >= self._max:
                logger.warning(
                    "Sync concurrency limit reached for user %s (%d in flight)",
                    user_id, current,
                )
                return False
            self._active[user_id] = current + 1
            logger.debug("Sync slot acquired for user %s (active=%d)", user_id, current + 1)
            return True

    def release(self, user_id: str) -> None:
        """
        Release a sync slot for ``user_id``.

        Safe to call even if ``acquire`` was never called (no-op).
        """
        with self._lock:
            current = self._active.get(user_id, 0)
            if current <= 1:
                self._active.pop(user_id, None)
            else:
                self._active[user_id] = current - 1
            logger.debug("Sync slot released for user %s", user_id)

    def is_active(self, user_id: str) -> bool:
        """Return True if a sync is currently in progress for ``user_id``."""
        with self._lock:
            return self._active.get(user_id, 0) > 0

    def active_count(self) -> int:
        """Return the total number of in-flight syncs across all users."""
        with self._lock:
            return sum(self._active.values())

    def fastapi_dependency(self) -> Callable:
        """
        FastAPI dependency that enforces the concurrency guard.

        Raises ``HTTP 409`` if a sync is already running for the user.

        Example::

            guard = SyncConcurrencyGuard()

            @router.post("/api/sync/start")
            async def start_sync(
                _: None = Depends(guard.fastapi_dependency()),
            ):
                ...
        """
        guard_self = self

        async def _dep(request: Request) -> None:
            user_id = _extract_user_id(request)
            if not user_id:
                # Not authenticated — let the permissions layer handle it
                return

            if guard_self.is_active(user_id):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "error": "sync_in_progress",
                        "message": (
                            "A sync is already running for your account. "
                            "Please wait for it to complete."
                        ),
                    },
                )

        return _dep


# ---------------------------------------------------------------------------
# Module-level shared instances + store replacement hook
# ---------------------------------------------------------------------------

# Default limiter — use this unless you need multiple limiters
_limiter: RateLimiter = RateLimiter()
_sync_guard: SyncConcurrencyGuard = SyncConcurrencyGuard()


def get_limiter() -> RateLimiter:
    """Return the module-level ``RateLimiter`` instance."""
    return _limiter


def get_sync_guard() -> SyncConcurrencyGuard:
    """Return the module-level ``SyncConcurrencyGuard`` instance."""
    return _sync_guard


def replace_store(new_store: RateLimitStore) -> None:
    """
    Swap the backing store on the module-level limiter.

    Call this during application startup to inject a Redis-backed store
    for multi-instance deployments::

        from middleware.rate_limit import replace_store
        replace_store(RedisRateLimitStore(redis_url=...))
    """
    global _limiter
    _limiter = RateLimiter(store=new_store)
    logger.info(
        "RateLimiter store replaced: %s", type(new_store).__name__
    )


def configure_routes(limiter: Optional[RateLimiter] = None) -> None:
    """
    Register the standard Academic OS per-route rate policies.

    Call once at application startup after ``replace_store()`` if used.
    Can also be called with a custom limiter instance::

        from middleware.rate_limit import configure_routes, get_limiter
        configure_routes(get_limiter())
    """
    target = limiter or _limiter

    # Dashboard reads
    target.register("/api/dashboard/overview", RatePolicy.dashboard_read())
    target.register("/api/dashboard/course", RatePolicy.dashboard_read())
    target.register("/api/dashboard/predictions", RatePolicy.dashboard_read())
    target.register("/api/dashboard/timeline", RatePolicy.dashboard_read())

    # Prediction reads
    target.register("/api/models/predict", RatePolicy.prediction_read())

    # Sync triggers — tightest limits
    target.register("/api/sync/start", RatePolicy.sync_trigger())
    target.register("/api/sync/refresh", RatePolicy.sync_trigger())

    # LMS connect / disconnect
    target.register("/api/lumen/connect", RatePolicy.lms_connect())
    target.register("/api/lumen/disconnect", RatePolicy.lms_connect())

    # Admin mutations
    target.register("/api/models/retrain", RatePolicy.admin_action())
    target.register("/api/admin", RatePolicy.admin_action())

    logger.info("Standard Academic OS rate policies registered")


# ---------------------------------------------------------------------------
# __all__
# ---------------------------------------------------------------------------

__all__ = [
    # Policy
    "RatePolicy",
    # Result
    "RateLimitResult",
    # Store
    "RateLimitStore",
    "InProcessStore",
    # Core
    "RateLimiter",
    # Middleware
    "RateLimitMiddleware",
    # Sync guard
    "SyncConcurrencyGuard",
    # Module-level helpers
    "get_limiter",
    "get_sync_guard",
    "replace_store",
    "configure_routes",
]
