"""Internal HTTP utilities shared with the async client.

Not a part of the public API, must import explicitly.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from .exceptions import (
    AuthError, NotFoundError, RateLimitError, ServerError, UrchinError
)


logger = logging.getLogger(__name__)

_RETRYABLE = frozenset({429, 500, 502, 503, 504})


def retry_after(response: aiohttp.ClientResponse) -> float | None:
    """Parse the Retry-After header into seconds, if present."""
    raw = response.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


async def raise_for_status(response: aiohttp.ClientResponse) -> None:
    """Map HTTP error codes to typed urchin-api exceptions."""
    code = response.status
    if code < 400:
        return
    if code == 401:
        raise AuthError("HTTP 401 - missing API key")
    if code == 403:
        raise AuthError("HTTP 403 - invalid API key")
    if code == 404:
        raise NotFoundError("HTTP 404 - resource not found")
    if code == 429:
        raise RateLimitError(
            "HTTP 429 - rate limit exceeded", retry_after(response)
        )
    if code >= 500:
        raise ServerError(f"HTTP {code} - server error", code)
    data = await response.json()
    raise UrchinError(f"HTTP {code} - {data.get('error', 'unexpected error')}")


async def request(
    session: aiohttp.ClientSession,
    method: str,
    url: str,
    *,
    max_retries: int = 3,
    backoff_base: float = 0.5,
    **kwargs: Any
) -> Any:
    """Perform an HTTP request, retrying on errors with exponential backoff.

    Raises an appropriate :class:`UrchinError` on failure.

    Returns:
        Parsed JSON body, or an empty dict if the response has no content.
    """
    last_exc: UrchinError | None = None

    for attempt in range(max_retries+1):
        try:
            async with session.request(method, url, **kwargs) as response:
                if response.status in _RETRYABLE and attempt < max_retries:
                    wait = backoff_base * (2**attempt)
                    if response.status == 429:
                        if (ra := retry_after(response)) is not None:
                            wait = ra
                    logger.debug(
                        f"Retryable HTTP {response.status} for {url} - "
                        f"waiting {wait:.3f}s ({attempt+1}/{max_retries})"
                    )
                    await asyncio.sleep(wait)
                    continue
                await raise_for_status(response)
                if response.content_length == 0 or response.status == 204:
                    return {}
                return await response.json(content_type=None)
        except (AuthError, NotFoundError):
            raise  # Don't attempt to retry authentication or not-found errors
        except (RateLimitError, ServerError) as e:
            last_exc = e
            if attempt < max_retries:
                wait = backoff_base * (2**attempt)
                if isinstance(e, RateLimitError) and e.retry_after:
                    wait = e.retry_after
                await asyncio.sleep(wait)
        except aiohttp.ClientConnectionError as e:
            last_exc = UrchinError(f"Connection error - {e}")
            if attempt < max_retries:
                await asyncio.sleep(backoff_base * (2**attempt))
        except aiohttp.ClientError as e:
            raise UrchinError(f"HTTP client error - {e}")

    raise last_exc or UrchinError("Request failed after retries")
