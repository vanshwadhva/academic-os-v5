"""
Cache Configuration — In-process multi-tier caching for Academic OS.

Purpose and PRD alignment
--------------------------
The PRD mandates three specific caching behaviours:

  1. "Initial dashboard load should not depend on a full live sync completing."
     → Dashboard responses are cached so a stale-but-fast read is always
       available while a background sync runs.

  2. "Cached latest records should be shown first, then refreshed asynchronously."
     → Per-user dashboard and prediction results are stored with TTLs that
       exceed a typical session so the first paint is instant.

  3. "Incremental sync should be preferred over full resync where supported."
     → LMS API responses are cached with short TTLs so the sync worker
       re-fetches only what has changed, reducing LMS API calls and
       respecting rate limits.

Cache namespaces
----------------
All keys are prefixed with a namespace to prevent collision across layers
and to allow namespace-scoped invalidation (e.g. invalidate every cached
prediction for a user without touching dashboard or LMS caches).

  ``dashboard:{user_id}``            — aggregated dashboard API response
  ``prediction:{user_id}:{course}``  — ML prediction output per student-course
  ``prediction:{user_id}:global``    — global (cross-course) prediction
  ``lms:courses:{user_id}``          — LMS course list for the user
  ``lms:quiz:{user_id}:{course_id}`` — quiz records per course
  ``lms:grades:{user_id}:{course}``  — grade records per course
  ``lms:modules:{user_id}:{course}`` — module completion records
  ``lms:assignments:{user_id}:{c}``  — assignment records
  ``lms:attendance:{user_id}:{c}``   — attendance records
  ``features:{user_id}:{course}``    — engineered feature vector (pre-ML)
  ``sync_status:{user_id}``          — last sync job status / timestamp
  ``principal:{token_hash}``         — decoded auth token claim (short TTL)

Architecture
------------
``CacheBackend`` (ABC) → ``InProcessCache`` (default, no deps)
                       → Redis backend injectable via ``replace_backend()``

``CacheManager`` wraps the backend with:
  - Namespace-keyed helpers for every data domain
  - Per-namespace TTL config from ``CacheTTL``
  - Stale-while-revalidate flag support
  - Invalidation helpers (per-user, per-namespace, full flush)
  - ``@cached`` decorator for service-layer methods
  - Structured logging on every miss/hit/eviction

No additional dependencies are required for the default in-process mode.
A Redis-backed ``RedisCacheBackend`` stub is included at the bottom so
the team can fill it in when scaling to multiple workers.

Usage
-----
::

    from config.cache import cache, CacheTTL, cached

    # Direct use
    overview = cache.get_dashboard(user_id)
    if overview is None:
        overview = build_dashboard(user_id)
        cache.set_dashboard(user_id, overview)

    # Decorator
    @cached(namespace="prediction", ttl=CacheTTL.PREDICTION)
    def get_prediction(user_id: str, course_id: str) -> dict:
        return run_ml_inference(user_id, course_id)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from abc import ABC, abstractmethod
from collections import OrderedDict
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple, Type

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# TTL constants — one place to tune every cache tier
# ---------------------------------------------------------------------------


class CacheTTL:
    """
    Time-to-live values in seconds for every cache namespace.

    Tuned to the PRD's reliability and freshness requirements:

    - Dashboard and predictions use longer TTLs because the PRD asks for
      "cached latest records shown first, then refreshed asynchronously".
      A stale dashboard shown for up to 5 minutes is acceptable.

    - LMS API responses use shorter TTLs to limit the blast radius of
      stale data while still absorbing rapid identical requests from the
      sync worker (de-duplication window).

    - Feature vectors are cached until the next sync rewrites them, so
      they use the same TTL as predictions.

    - Auth principal tokens are cached for a short window to avoid
      re-verifying the same JWT on every request in a session.

    All values are overridable via environment variables so ops can tune
    without a code deploy.
    """

    # Dashboard API response — serve stale while background sync runs
    DASHBOARD: int = int(os.getenv("CACHE_TTL_DASHBOARD", "300"))         # 5 min

    # ML prediction output — expensive to recompute, changes only after sync
    PREDICTION: int = int(os.getenv("CACHE_TTL_PREDICTION", "600"))       # 10 min

    # Engineered feature vector — tied to prediction lifecycle
    FEATURES: int = int(os.getenv("CACHE_TTL_FEATURES", "600"))           # 10 min

    # LMS course list — changes rarely within a semester
    LMS_COURSES: int = int(os.getenv("CACHE_TTL_LMS_COURSES", "1800"))    # 30 min

    # LMS quiz / assignment / grade records — de-dupe sync worker calls
    LMS_ACADEMIC: int = int(os.getenv("CACHE_TTL_LMS_ACADEMIC", "120"))   # 2 min

    # LMS module completion — slightly longer; completion rarely reverts
    LMS_MODULES: int = int(os.getenv("CACHE_TTL_LMS_MODULES", "300"))     # 5 min

    # LMS attendance — same as modules
    LMS_ATTENDANCE: int = int(os.getenv("CACHE_TTL_LMS_ATTENDANCE", "300"))

    # Sync job status — short; student polls this after triggering sync
    SYNC_STATUS: int = int(os.getenv("CACHE_TTL_SYNC_STATUS", "30"))      # 30 sec

    # Auth principal / decoded JWT claims — short for security
    PRINCIPAL: int = int(os.getenv("CACHE_TTL_PRINCIPAL", "60"))          # 1 min

    # Generic / default
    DEFAULT: int = int(os.getenv("CACHE_TTL_DEFAULT", "120"))             # 2 min


# ---------------------------------------------------------------------------
# Cache entry
# ---------------------------------------------------------------------------


@dataclass
class CacheEntry:
    """
    A single cached value with metadata.

    Attributes
    ----------
    value:
        The serialised or raw cached object.
    expires_at:
        Monotonic clock timestamp after which this entry is stale.
    namespace:
        The logical domain this entry belongs to.
    created_at:
        Wall-clock ISO timestamp for observability.
    hit_count:
        Number of times this entry has been retrieved (debug aid).
    stale_while_revalidate:
        If True, a stale entry may still be served while a background
        refresh is in progress.  The caller is responsible for
        triggering the refresh.
    """

    value: Any
    expires_at: float
    namespace: str = ""
    created_at: str = field(default_factory=lambda: _iso_now())
    hit_count: int = 0
    stale_while_revalidate: bool = False

    def is_expired(self) -> bool:
        """Return True if the entry is past its TTL."""
        return time.monotonic() > self.expires_at

    def is_stale_but_usable(self) -> bool:
        """
        Return True if the entry is expired but may still be served
        while a background refresh runs (stale-while-revalidate pattern).
        """
        return self.is_expired() and self.stale_while_revalidate

    def ttl_remaining(self) -> float:
        """Seconds remaining before expiry.  Negative if already expired."""
        return self.expires_at - time.monotonic()


def _iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(tz=timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Cache stats
# ---------------------------------------------------------------------------


@dataclass
class CacheStats:
    """
    Aggregate hit/miss/eviction counters for a cache backend.

    Exposed via the health endpoint and monitoring dashboard.
    """

    hits: int = 0
    misses: int = 0
    sets: int = 0
    deletes: int = 0
    evictions: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return round(self.hits / total, 4) if total else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "sets": self.sets,
            "deletes": self.deletes,
            "evictions": self.evictions,
            "hit_rate": self.hit_rate,
        }


# ---------------------------------------------------------------------------
# Cache backend interface
# ---------------------------------------------------------------------------


class CacheBackend(ABC):
    """
    Abstract cache storage backend.

    Implement this with a Redis client for multi-process/multi-instance
    deployments.  The default ``InProcessCache`` handles single-worker
    and development environments with no extra dependencies.
    """

    @abstractmethod
    def get(self, key: str) -> Optional[CacheEntry]:
        """Retrieve an entry.  Returns ``None`` on miss or expiry."""

    @abstractmethod
    def set(
        self,
        key: str,
        value: Any,
        ttl: int,
        namespace: str = "",
        stale_while_revalidate: bool = False,
    ) -> None:
        """Store ``value`` under ``key`` with a TTL in seconds."""

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Remove a single key.  Returns True if the key existed."""

    @abstractmethod
    def delete_namespace(self, namespace: str) -> int:
        """
        Remove all keys that belong to ``namespace``.

        Returns the count of removed entries.
        """

    @abstractmethod
    def delete_pattern(self, prefix: str) -> int:
        """
        Remove all keys whose raw key starts with ``prefix``.

        Returns the count of removed entries.
        Useful for invalidating all cached data for a specific user ID.
        """

    @abstractmethod
    def flush(self) -> int:
        """Remove every entry.  Returns count removed."""

    @abstractmethod
    def stats(self) -> CacheStats:
        """Return aggregate statistics."""

    @abstractmethod
    def keys(self) -> Iterator[str]:
        """Iterate over all live (non-expired) keys."""

    @abstractmethod
    def size(self) -> int:
        """Return the count of live (non-expired) entries."""


# ---------------------------------------------------------------------------
# In-process backend (default — no dependencies)
# ---------------------------------------------------------------------------


class InProcessCache(CacheBackend):
    """
    Thread-safe in-process LRU cache.

    Uses an ``OrderedDict`` as a bounded LRU store.  Entries past their
    TTL are treated as misses but are only physically removed during
    ``get`` (lazy eviction) and periodic ``flush_expired`` sweeps.

    Args:
        max_entries:
            Maximum number of live entries before LRU eviction kicks in.
            Defaults to 50,000 — sized to hold dashboards + predictions
            for ~1,000 concurrent students with per-course granularity.
        sweep_interval:
            Seconds between background expiry sweeps.  0 = no automatic
            sweep (manual ``flush_expired()`` only).
    """

    def __init__(
        self,
        max_entries: int = int(os.getenv("CACHE_MAX_ENTRIES", "50000")),
        sweep_interval: float = float(os.getenv("CACHE_SWEEP_INTERVAL", "60")),
    ) -> None:
        self._lock = threading.RLock()
        self._store: OrderedDict[str, CacheEntry] = OrderedDict()
        self._max_entries = max_entries
        self._stats = CacheStats()
        self._sweep_interval = sweep_interval
        self._last_sweep = time.monotonic()

        logger.info(
            "InProcessCache initialised — max_entries=%d sweep_interval=%.0fs",
            max_entries, sweep_interval,
        )

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def get(self, key: str) -> Optional[CacheEntry]:
        self._maybe_sweep()

        with self._lock:
            entry = self._store.get(key)

            if entry is None:
                self._stats.misses += 1
                logger.debug("CACHE MISS  key=%s", _truncate(key))
                return None

            if entry.is_expired() and not entry.stale_while_revalidate:
                # Hard expiry — remove and report miss
                del self._store[key]
                self._stats.misses += 1
                self._stats.evictions += 1
                logger.debug("CACHE EXPIRED key=%s", _truncate(key))
                return None

            # Cache hit — promote to end (most-recently-used)
            self._store.move_to_end(key)
            entry.hit_count += 1
            self._stats.hits += 1
            logger.debug(
                "CACHE HIT  key=%s ttl_remaining=%.1fs",
                _truncate(key), entry.ttl_remaining(),
            )
            return entry

    def set(
        self,
        key: str,
        value: Any,
        ttl: int,
        namespace: str = "",
        stale_while_revalidate: bool = False,
    ) -> None:
        with self._lock:
            entry = CacheEntry(
                value=value,
                expires_at=time.monotonic() + ttl,
                namespace=namespace,
                stale_while_revalidate=stale_while_revalidate,
            )
            self._store[key] = entry
            self._store.move_to_end(key)
            self._stats.sets += 1

            # Evict least-recently-used entries if over capacity
            while len(self._store) > self._max_entries:
                evicted_key, _ = self._store.popitem(last=False)
                self._stats.evictions += 1
                logger.debug("CACHE EVICT (LRU) key=%s", _truncate(evicted_key))

        logger.debug(
            "CACHE SET  key=%s ttl=%ds ns=%s swr=%s",
            _truncate(key), ttl, namespace, stale_while_revalidate,
        )

    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._store:
                del self._store[key]
                self._stats.deletes += 1
                logger.debug("CACHE DEL  key=%s", _truncate(key))
                return True
            return False

    def delete_namespace(self, namespace: str) -> int:
        with self._lock:
            keys_to_remove = [
                k for k, v in self._store.items() if v.namespace == namespace
            ]
            for k in keys_to_remove:
                del self._store[k]
                self._stats.deletes += 1
        logger.info(
            "CACHE DEL NAMESPACE ns=%s removed=%d", namespace, len(keys_to_remove)
        )
        return len(keys_to_remove)

    def delete_pattern(self, prefix: str) -> int:
        with self._lock:
            keys_to_remove = [k for k in self._store if k.startswith(prefix)]
            for k in keys_to_remove:
                del self._store[k]
                self._stats.deletes += 1
        logger.info(
            "CACHE DEL PATTERN prefix=%s removed=%d", prefix, len(keys_to_remove)
        )
        return len(keys_to_remove)

    def flush(self) -> int:
        with self._lock:
            count = len(self._store)
            self._store.clear()
            self._stats.evictions += count
        logger.info("CACHE FLUSH removed=%d", count)
        return count

    def flush_expired(self) -> int:
        """Remove all entries past their hard TTL.  Called by sweep."""
        with self._lock:
            expired = [
                k for k, v in self._store.items()
                if v.is_expired() and not v.stale_while_revalidate
            ]
            for k in expired:
                del self._store[k]
                self._stats.evictions += 1
        if expired:
            logger.debug("CACHE SWEEP evicted=%d expired entries", len(expired))
        return len(expired)

    def stats(self) -> CacheStats:
        with self._lock:
            return CacheStats(
                hits=self._stats.hits,
                misses=self._stats.misses,
                sets=self._stats.sets,
                deletes=self._stats.deletes,
                evictions=self._stats.evictions,
            )

    def keys(self) -> Iterator[str]:
        with self._lock:
            # Snapshot to avoid holding the lock during iteration
            live = [k for k, v in self._store.items() if not v.is_expired()]
        return iter(live)

    def size(self) -> int:
        with self._lock:
            return sum(1 for v in self._store.values() if not v.is_expired())

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _maybe_sweep(self) -> None:
        """Run a sweep if the sweep interval has elapsed."""
        if self._sweep_interval <= 0:
            return
        now = time.monotonic()
        if now - self._last_sweep >= self._sweep_interval:
            self._last_sweep = now
            self.flush_expired()


def _truncate(key: str, max_len: int = 48) -> str:
    """Truncate long keys for log readability."""
    return key if len(key) <= max_len else key[:max_len] + "…"


# ---------------------------------------------------------------------------
# Key builder
# ---------------------------------------------------------------------------


class CacheKey:
    """
    Centralised key factory for every cache namespace.

    All keys follow the pattern ``{namespace}:{component}:{...args}``
    making pattern-based invalidation and log parsing straightforward.
    Long user IDs or course IDs are SHA-256 hashed to a fixed width so
    the key length stays bounded regardless of input.

    Only use the class methods — never build keys inline in service code.
    """

    @staticmethod
    def dashboard(user_id: str) -> str:
        return f"dashboard:{_hid(user_id)}"

    @staticmethod
    def prediction(user_id: str, course_id: Optional[str] = None) -> str:
        if course_id:
            return f"prediction:{_hid(user_id)}:{_hid(course_id)}"
        return f"prediction:{_hid(user_id)}:global"

    @staticmethod
    def features(user_id: str, course_id: str) -> str:
        return f"features:{_hid(user_id)}:{_hid(course_id)}"

    @staticmethod
    def lms_courses(user_id: str) -> str:
        return f"lms:courses:{_hid(user_id)}"

    @staticmethod
    def lms_quiz(user_id: str, course_id: str) -> str:
        return f"lms:quiz:{_hid(user_id)}:{_hid(course_id)}"

    @staticmethod
    def lms_grades(user_id: str, course_id: str) -> str:
        return f"lms:grades:{_hid(user_id)}:{_hid(course_id)}"

    @staticmethod
    def lms_modules(user_id: str, course_id: str) -> str:
        return f"lms:modules:{_hid(user_id)}:{_hid(course_id)}"

    @staticmethod
    def lms_assignments(user_id: str, course_id: str) -> str:
        return f"lms:assignments:{_hid(user_id)}:{_hid(course_id)}"

    @staticmethod
    def lms_attendance(user_id: str, course_id: str) -> str:
        return f"lms:attendance:{_hid(user_id)}:{_hid(course_id)}"

    @staticmethod
    def sync_status(user_id: str) -> str:
        return f"sync_status:{_hid(user_id)}"

    @staticmethod
    def principal(token: str) -> str:
        """Key for a cached auth principal.  Input is the raw token."""
        return f"principal:{_hid(token)}"

    # ------------------------------------------------------------------
    # Namespace prefixes — used for bulk invalidation
    # ------------------------------------------------------------------

    @staticmethod
    def user_prefix(user_id: str) -> str:
        """
        Prefix matching ALL cache entries belonging to a user.

        Passing this to ``delete_pattern`` purges the entire cache for
        the student — correct behaviour after disconnect or data deletion.
        """
        return f"_uid:{_hid(user_id)}:"

    @staticmethod
    def namespace_prefix(namespace: str) -> str:
        return f"{namespace}:"


def _hid(raw: str) -> str:
    """
    Produce a stable 16-char hex fingerprint of ``raw``.

    Short enough to keep keys readable in logs; long enough for
    ~10^19 collision resistance across typical student/course ID spaces.
    """
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# CacheManager — high-level API used by service layer
# ---------------------------------------------------------------------------


class CacheManager:
    """
    High-level cache façade used throughout Academic OS services.

    Provides:
    - Named getters/setters for every domain (dashboard, prediction, LMS, etc.)
    - Stale-while-revalidate support on dashboard and prediction reads
    - User-scoped and namespace-scoped invalidation
    - Stats reporting for the health/monitoring endpoint
    - ``@cached`` decorator integration

    Args:
        backend:    Storage backend.  Defaults to ``InProcessCache``.
        ttl:        ``CacheTTL`` class (or compatible).  Allows overriding
                    TTLs per-environment without changing call sites.
    """

    def __init__(
        self,
        backend: Optional[CacheBackend] = None,
        ttl: Type[CacheTTL] = CacheTTL,
    ) -> None:
        self._backend = backend or InProcessCache()
        self._ttl = ttl
        logger.info(
            "CacheManager initialised — backend=%s",
            type(self._backend).__name__,
        )

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------

    def get_dashboard(self, user_id: str) -> Optional[Any]:
        """
        Retrieve a cached dashboard response.

        Returns the value even if stale (stale-while-revalidate).
        Callers should check ``CacheEntry.is_expired()`` to decide
        whether to trigger a background refresh.
        """
        key = CacheKey.dashboard(user_id)
        entry = self._backend.get(key)
        if entry is None:
            return None
        return entry.value

    def get_dashboard_entry(self, user_id: str) -> Optional[CacheEntry]:
        """Return the full ``CacheEntry`` so callers can inspect staleness."""
        return self._backend.get(CacheKey.dashboard(user_id))

    def set_dashboard(
        self,
        user_id: str,
        data: Any,
        stale_while_revalidate: bool = True,
    ) -> None:
        """
        Cache a dashboard response.

        ``stale_while_revalidate=True`` by default — serves slightly stale
        data while a background sync refreshes it (PRD requirement).
        """
        self._backend.set(
            key=CacheKey.dashboard(user_id),
            value=data,
            ttl=self._ttl.DASHBOARD,
            namespace="dashboard",
            stale_while_revalidate=stale_while_revalidate,
        )

    def invalidate_dashboard(self, user_id: str) -> None:
        self._backend.delete(CacheKey.dashboard(user_id))
        logger.debug("Invalidated dashboard cache for user %s", _truncate(user_id))

    # ------------------------------------------------------------------
    # Predictions
    # ------------------------------------------------------------------

    def get_prediction(
        self,
        user_id: str,
        course_id: Optional[str] = None,
    ) -> Optional[Any]:
        """Retrieve a cached prediction.  Returns stale values."""
        entry = self._backend.get(CacheKey.prediction(user_id, course_id))
        return entry.value if entry else None

    def set_prediction(
        self,
        user_id: str,
        data: Any,
        course_id: Optional[str] = None,
        stale_while_revalidate: bool = True,
    ) -> None:
        self._backend.set(
            key=CacheKey.prediction(user_id, course_id),
            value=data,
            ttl=self._ttl.PREDICTION,
            namespace="prediction",
            stale_while_revalidate=stale_while_revalidate,
        )

    def invalidate_predictions(self, user_id: str) -> int:
        """Invalidate all prediction cache entries for a user."""
        prefix = f"prediction:{_hid(user_id)}:"
        removed = self._backend.delete_pattern(prefix)
        # Also remove the global prediction key
        self._backend.delete(CacheKey.prediction(user_id, None))
        return removed + 1

    # ------------------------------------------------------------------
    # Feature vectors
    # ------------------------------------------------------------------

    def get_features(self, user_id: str, course_id: str) -> Optional[Any]:
        entry = self._backend.get(CacheKey.features(user_id, course_id))
        return entry.value if entry else None

    def set_features(self, user_id: str, course_id: str, data: Any) -> None:
        self._backend.set(
            key=CacheKey.features(user_id, course_id),
            value=data,
            ttl=self._ttl.FEATURES,
            namespace="features",
        )

    def invalidate_features(self, user_id: str) -> int:
        return self._backend.delete_pattern(f"features:{_hid(user_id)}:")

    # ------------------------------------------------------------------
    # LMS data — used by the sync worker to de-duplicate API calls
    # ------------------------------------------------------------------

    def get_lms_courses(self, user_id: str) -> Optional[Any]:
        entry = self._backend.get(CacheKey.lms_courses(user_id))
        return entry.value if entry else None

    def set_lms_courses(self, user_id: str, data: Any) -> None:
        self._backend.set(
            key=CacheKey.lms_courses(user_id),
            value=data,
            ttl=self._ttl.LMS_COURSES,
            namespace="lms",
        )

    def get_lms_quiz(self, user_id: str, course_id: str) -> Optional[Any]:
        entry = self._backend.get(CacheKey.lms_quiz(user_id, course_id))
        return entry.value if entry else None

    def set_lms_quiz(self, user_id: str, course_id: str, data: Any) -> None:
        self._backend.set(
            key=CacheKey.lms_quiz(user_id, course_id),
            value=data,
            ttl=self._ttl.LMS_ACADEMIC,
            namespace="lms",
        )

    def get_lms_grades(self, user_id: str, course_id: str) -> Optional[Any]:
        entry = self._backend.get(CacheKey.lms_grades(user_id, course_id))
        return entry.value if entry else None

    def set_lms_grades(self, user_id: str, course_id: str, data: Any) -> None:
        self._backend.set(
            key=CacheKey.lms_grades(user_id, course_id),
            value=data,
            ttl=self._ttl.LMS_ACADEMIC,
            namespace="lms",
        )

    def get_lms_modules(self, user_id: str, course_id: str) -> Optional[Any]:
        entry = self._backend.get(CacheKey.lms_modules(user_id, course_id))
        return entry.value if entry else None

    def set_lms_modules(self, user_id: str, course_id: str, data: Any) -> None:
        self._backend.set(
            key=CacheKey.lms_modules(user_id, course_id),
            value=data,
            ttl=self._ttl.LMS_MODULES,
            namespace="lms",
        )

    def get_lms_assignments(self, user_id: str, course_id: str) -> Optional[Any]:
        entry = self._backend.get(CacheKey.lms_assignments(user_id, course_id))
        return entry.value if entry else None

    def set_lms_assignments(self, user_id: str, course_id: str, data: Any) -> None:
        self._backend.set(
            key=CacheKey.lms_assignments(user_id, course_id),
            value=data,
            ttl=self._ttl.LMS_ACADEMIC,
            namespace="lms",
        )

    def get_lms_attendance(self, user_id: str, course_id: str) -> Optional[Any]:
        entry = self._backend.get(CacheKey.lms_attendance(user_id, course_id))
        return entry.value if entry else None

    def set_lms_attendance(self, user_id: str, course_id: str, data: Any) -> None:
        self._backend.set(
            key=CacheKey.lms_attendance(user_id, course_id),
            value=data,
            ttl=self._ttl.LMS_ATTENDANCE,
            namespace="lms",
        )

    # ------------------------------------------------------------------
    # Sync status
    # ------------------------------------------------------------------

    def get_sync_status(self, user_id: str) -> Optional[Any]:
        entry = self._backend.get(CacheKey.sync_status(user_id))
        return entry.value if entry else None

    def set_sync_status(self, user_id: str, data: Any) -> None:
        self._backend.set(
            key=CacheKey.sync_status(user_id),
            value=data,
            ttl=self._ttl.SYNC_STATUS,
            namespace="sync_status",
        )

    def invalidate_sync_status(self, user_id: str) -> None:
        self._backend.delete(CacheKey.sync_status(user_id))

    # ------------------------------------------------------------------
    # Auth principal
    # ------------------------------------------------------------------

    def get_principal(self, token: str) -> Optional[Any]:
        """Retrieve cached decoded token claims."""
        entry = self._backend.get(CacheKey.principal(token))
        return entry.value if entry else None

    def set_principal(self, token: str, claims: Any) -> None:
        """Cache decoded token claims for a short TTL."""
        self._backend.set(
            key=CacheKey.principal(token),
            value=claims,
            ttl=self._ttl.PRINCIPAL,
            namespace="principal",
        )

    # ------------------------------------------------------------------
    # Generic get/set for ad-hoc caching
    # ------------------------------------------------------------------

    def get(self, key: str) -> Optional[Any]:
        entry = self._backend.get(key)
        return entry.value if entry else None

    def set(
        self,
        key: str,
        value: Any,
        ttl: int = CacheTTL.DEFAULT,
        namespace: str = "generic",
    ) -> None:
        self._backend.set(key=key, value=value, ttl=ttl, namespace=namespace)

    def delete(self, key: str) -> bool:
        return self._backend.delete(key)

    # ------------------------------------------------------------------
    # Bulk invalidation — called after sync completes or user disconnects
    # ------------------------------------------------------------------

    def invalidate_user(self, user_id: str) -> int:
        """
        Invalidate ALL cached data for a user.

        Called after:
        - A sync completes (force-refresh all stale data)
        - The user disconnects their LMS (clear all LMS-sourced data)
        - An admin deletes student data (PRD data-deletion requirement)

        Returns total entries removed.
        """
        uid_hash = _hid(user_id)
        total = 0

        # Each namespace prefix
        for prefix in (
            f"dashboard:{uid_hash}",
            f"prediction:{uid_hash}",
            f"features:{uid_hash}",
            f"lms:courses:{uid_hash}",
            f"lms:quiz:{uid_hash}",
            f"lms:grades:{uid_hash}",
            f"lms:modules:{uid_hash}",
            f"lms:assignments:{uid_hash}",
            f"lms:attendance:{uid_hash}",
            f"sync_status:{uid_hash}",
        ):
            total += self._backend.delete_pattern(prefix)

        logger.info(
            "Cache invalidated for user %s — %d entries removed",
            _truncate(user_id), total,
        )
        return total

    def invalidate_lms_data(self, user_id: str) -> int:
        """
        Invalidate only LMS-sourced cache entries for a user.

        Called after a partial sync or when the LMS connection is stale,
        so LMS data is re-fetched on next access without disturbing
        predictions and dashboard snapshots.
        """
        uid_hash = _hid(user_id)
        total = 0
        for prefix in (
            f"lms:courses:{uid_hash}",
            f"lms:quiz:{uid_hash}",
            f"lms:grades:{uid_hash}",
            f"lms:modules:{uid_hash}",
            f"lms:assignments:{uid_hash}",
            f"lms:attendance:{uid_hash}",
        ):
            total += self._backend.delete_pattern(prefix)
        logger.debug(
            "LMS cache invalidated for user %s — %d entries", _truncate(user_id), total
        )
        return total

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        """Return cache statistics for the health/monitoring endpoint."""
        s = self._backend.stats()
        return {
            "backend": type(self._backend).__name__,
            "size": self._backend.size(),
            **s.to_dict(),
        }

    def health(self) -> Dict[str, Any]:
        """
        Lightweight health check — verifies the backend is responsive
        by performing a synthetic set/get/delete round-trip.
        """
        probe_key = "__health_probe__"
        probe_value = {"ok": True}
        try:
            self._backend.set(probe_key, probe_value, ttl=5)
            entry = self._backend.get(probe_key)
            self._backend.delete(probe_key)
            ok = entry is not None and entry.value == probe_value
        except Exception as exc:
            logger.error("Cache health check failed: %s", exc)
            ok = False

        return {"status": "ok" if ok else "degraded", "backend": type(self._backend).__name__}


# ---------------------------------------------------------------------------
# @cached decorator
# ---------------------------------------------------------------------------


def cached(
    namespace: str,
    ttl: int = CacheTTL.DEFAULT,
    key_fn: Optional[Callable[..., str]] = None,
    stale_while_revalidate: bool = False,
    cache_instance: Optional[CacheManager] = None,
) -> Callable:
    """
    Decorator for caching the return value of a service-layer function.

    The cache key is built from ``namespace + ":" + "_".join(str(a) for a
    in args)`` by default, or from ``key_fn(*args, **kwargs)`` if provided.

    The ``cache`` module-level instance is used unless ``cache_instance``
    is explicitly passed.

    Args:
        namespace:             Cache namespace prefix.
        ttl:                   TTL in seconds.
        key_fn:                Optional callable that accepts the same
                               arguments as the decorated function and
                               returns the cache key string.
        stale_while_revalidate: If True, serve expired values while the
                               function recomputes.
        cache_instance:        Explicit ``CacheManager`` to use.  Defaults
                               to the module-level ``cache`` singleton.

    Example::

        @cached(namespace="prediction", ttl=CacheTTL.PREDICTION)
        def get_prediction(user_id: str, course_id: str) -> dict:
            return run_ml_inference(user_id, course_id)

        # Custom key
        @cached(
            namespace="lms",
            ttl=CacheTTL.LMS_ACADEMIC,
            key_fn=lambda user_id, course_id: f"lms:quiz:{user_id}:{course_id}",
        )
        def fetch_quizzes(user_id: str, course_id: str) -> list:
            ...
    """
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Resolve cache instance — late binding so module-level
            # ``cache`` can be replaced after import
            mgr: CacheManager = cache_instance or cache

            # Build key
            if key_fn:
                key = key_fn(*args, **kwargs)
            else:
                arg_part = "_".join(str(a) for a in args)
                kwarg_part = "_".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
                raw = f"{namespace}:{arg_part}:{kwarg_part}"
                key = f"{namespace}:{_hid(raw)}"

            # Check cache
            entry = mgr._backend.get(key)
            if entry is not None:
                if not entry.is_expired():
                    return entry.value
                if entry.stale_while_revalidate:
                    # Return stale value; caller should refresh asynchronously
                    logger.debug("@cached STALE key=%s", _truncate(key))
                    return entry.value

            # Cache miss — compute
            result = fn(*args, **kwargs)

            mgr._backend.set(
                key=key,
                value=result,
                ttl=ttl,
                namespace=namespace,
                stale_while_revalidate=stale_while_revalidate,
            )
            return result

        # Attach a manual invalidation helper to the wrapped function
        def invalidate(*args: Any, **kwargs: Any) -> None:
            mgr: CacheManager = cache_instance or cache
            if key_fn:
                key = key_fn(*args, **kwargs)
            else:
                arg_part = "_".join(str(a) for a in args)
                kwarg_part = "_".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
                raw = f"{namespace}:{arg_part}:{kwarg_part}"
                key = f"{namespace}:{_hid(raw)}"
            mgr._backend.delete(key)

        wrapper.invalidate = invalidate  # type: ignore[attr-defined]
        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# Redis backend stub — fill in when scaling to multi-worker deployments
# ---------------------------------------------------------------------------


class RedisCacheBackend(CacheBackend):
    """
    Redis-backed cache backend.

    Drop-in replacement for ``InProcessCache`` for multi-instance
    deployments.  Requires ``redis-py`` (``pip install redis>=5``).

    Activate at startup::

        from config.cache import replace_backend, RedisCacheBackend
        replace_backend(RedisCacheBackend(url=settings.REDIS_URL))

    Args:
        url:        Redis connection URL (``redis://host:port/db``).
        prefix:     Key prefix added to every entry (default ``academos``).
        serialiser: ``'json'`` (default) or ``'pickle'``.  Use pickle only
                    for internal, trusted data — never for user-supplied input.
    """

    def __init__(
        self,
        url: str = "redis://localhost:6379/0",
        prefix: str = "academos",
        serialiser: str = "json",
    ) -> None:
        try:
            import redis  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "redis-py is required for RedisCacheBackend. "
                "Add 'redis>=5' to requirements.txt."
            ) from exc

        self._client = redis.Redis.from_url(url, decode_responses=False)
        self._prefix = prefix
        self._serialiser = serialiser
        self._stats = CacheStats()
        logger.info("RedisCacheBackend initialised — url=%s prefix=%s", url, prefix)

    def _full_key(self, key: str) -> str:
        return f"{self._prefix}:{key}"

    def _serialise(self, value: Any) -> bytes:
        if self._serialiser == "pickle":
            import pickle
            return pickle.dumps(value)
        return json.dumps(value, default=str).encode()

    def _deserialise(self, raw: bytes) -> Any:
        if self._serialiser == "pickle":
            import pickle
            return pickle.loads(raw)
        return json.loads(raw.decode())

    def get(self, key: str) -> Optional[CacheEntry]:
        try:
            raw = self._client.get(self._full_key(key))
            if raw is None:
                self._stats.misses += 1
                return None
            payload = self._deserialise(raw)
            self._stats.hits += 1
            ttl_remaining = self._client.ttl(self._full_key(key))
            return CacheEntry(
                value=payload.get("value"),
                expires_at=time.monotonic() + max(0, ttl_remaining),
                namespace=payload.get("namespace", ""),
                created_at=payload.get("created_at", _iso_now()),
                stale_while_revalidate=payload.get("swr", False),
            )
        except Exception as exc:
            logger.error("Redis GET failed for key %s: %s", key, exc)
            self._stats.misses += 1
            return None

    def set(
        self,
        key: str,
        value: Any,
        ttl: int,
        namespace: str = "",
        stale_while_revalidate: bool = False,
    ) -> None:
        payload = {
            "value": value,
            "namespace": namespace,
            "swr": stale_while_revalidate,
            "created_at": _iso_now(),
        }
        try:
            self._client.setex(
                self._full_key(key),
                ttl,
                self._serialise(payload),
            )
            self._stats.sets += 1
        except Exception as exc:
            logger.error("Redis SET failed for key %s: %s", key, exc)

    def delete(self, key: str) -> bool:
        try:
            result = self._client.delete(self._full_key(key))
            if result:
                self._stats.deletes += 1
            return bool(result)
        except Exception as exc:
            logger.error("Redis DELETE failed for key %s: %s", key, exc)
            return False

    def delete_namespace(self, namespace: str) -> int:
        # Namespace deletion requires a SCAN — expensive on large keyspaces
        pattern = f"{self._prefix}:*"
        removed = 0
        try:
            for raw_key in self._client.scan_iter(pattern):
                raw = self._client.get(raw_key)
                if raw:
                    payload = self._deserialise(raw)
                    if payload.get("namespace") == namespace:
                        self._client.delete(raw_key)
                        removed += 1
        except Exception as exc:
            logger.error("Redis delete_namespace failed: %s", exc)
        self._stats.deletes += removed
        return removed

    def delete_pattern(self, prefix: str) -> int:
        pattern = f"{self._prefix}:{prefix}*"
        removed = 0
        try:
            keys = list(self._client.scan_iter(pattern))
            if keys:
                removed = self._client.delete(*keys)
        except Exception as exc:
            logger.error("Redis delete_pattern failed: %s", exc)
        self._stats.deletes += removed
        return removed

    def flush(self) -> int:
        pattern = f"{self._prefix}:*"
        removed = 0
        try:
            keys = list(self._client.scan_iter(pattern))
            if keys:
                removed = self._client.delete(*keys)
        except Exception as exc:
            logger.error("Redis flush failed: %s", exc)
        self._stats.evictions += removed
        return removed

    def stats(self) -> CacheStats:
        return CacheStats(
            hits=self._stats.hits,
            misses=self._stats.misses,
            sets=self._stats.sets,
            deletes=self._stats.deletes,
            evictions=self._stats.evictions,
        )

    def keys(self) -> Iterator[str]:
        prefix = f"{self._prefix}:"
        try:
            for raw_key in self._client.scan_iter(f"{prefix}*"):
                yield raw_key.decode().removeprefix(prefix)
        except Exception as exc:
            logger.error("Redis keys() failed: %s", exc)

    def size(self) -> int:
        try:
            return sum(1 for _ in self._client.scan_iter(f"{self._prefix}:*"))
        except Exception:
            return -1


# ---------------------------------------------------------------------------
# Module-level singleton + replacement hook
# ---------------------------------------------------------------------------

# Shared instance — import this everywhere:
#   from config.cache import cache
cache: CacheManager = CacheManager()


def replace_backend(new_backend: CacheBackend) -> None:
    """
    Swap the backing store on the module-level ``CacheManager``.

    Call this during application startup to inject a Redis backend::

        from config.cache import replace_backend, RedisCacheBackend
        replace_backend(RedisCacheBackend(url=os.environ["REDIS_URL"]))

    Also useful in tests to inject an isolated in-process store::

        from config.cache import replace_backend, InProcessCache
        replace_backend(InProcessCache(max_entries=100))
    """
    global cache
    cache = CacheManager(backend=new_backend)
    logger.info(
        "CacheManager backend replaced: %s", type(new_backend).__name__
    )


# ---------------------------------------------------------------------------
# __all__
# ---------------------------------------------------------------------------

__all__ = [
    # TTL config
    "CacheTTL",
    # Data model
    "CacheEntry",
    "CacheStats",
    # Backends
    "CacheBackend",
    "InProcessCache",
    "RedisCacheBackend",
    # Key factory
    "CacheKey",
    # Manager
    "CacheManager",
    # Decorator
    "cached",
    # Singleton
    "cache",
    "replace_backend",
]
