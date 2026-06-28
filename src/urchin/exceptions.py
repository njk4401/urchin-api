"""Urchin API exceptions."""

from __future__ import annotations


class UrchinError(Exception):
    """Base exception for all Urchin API errors."""

class AuthError(UrchinError):
    """API key is missing, invalid, or lacks permission. (HTTP 401/403)"""

class NotFoundError(UrchinError):
    """The requested player or resource does not exist. (HTTP 404)"""

class RateLimitError(UrchinError):
    """Rate limit exceeded. Back off before retrying. (HTTP 429)"""
    def __init__(self, message: str, retry_after: float = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after

class ServerError(UrchinError):
    """Urchin server returned a 5xx error."""
    def __init__(self, message: str, status: int) -> None:
        super().__init__(message)
        self.status = status
