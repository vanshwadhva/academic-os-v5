"""Runtime configuration for Lumen/Brightspace API clients."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class LumenConfig:
    version: str = "1.0"
    le_version: str = "1.55"
    max_retries: int = int(os.getenv("LUMEN_MAX_RETRIES", "3"))
    backoff_factor: float = float(os.getenv("LUMEN_BACKOFF_FACTOR", "0.5"))
    request_timeout: int = int(os.getenv("LUMEN_REQUEST_TIMEOUT", "30"))
    request_delay: float = float(os.getenv("LUMEN_REQUEST_DELAY", "0.15"))
    oauth_scopes: str = os.getenv(
        "LUMEN_OAUTH_SCOPES",
        "core:*:* enrollment:*:* grades:*:* content:*:* quizzing:*:* dropbox:*:* attendance:*:*",
    )
