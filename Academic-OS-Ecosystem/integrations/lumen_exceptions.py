"""Shared exceptions for the Lumen/Brightspace integration package."""


class LumenError(Exception):
    """Base class for Lumen integration errors."""


class LumenAuthError(LumenError):
    """Raised when Lumen authentication or authorization fails."""


class LumenAPIError(LumenError):
    """Raised when a Brightspace API request fails."""


class LumenRateLimitError(LumenAPIError):
    """Raised when the Brightspace tenant rate-limits requests."""


class LumenTokenExpiredError(LumenAuthError):
    """Raised when an access token is expired and cannot be refreshed."""
