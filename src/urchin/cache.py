"""Internal Cache structure utilized by the async client.

Not a part of the public API, must import explicitly.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any


class Cache:
    """Class for caching API responses to avoid spamming requests."""
    def __init__(self, lifetime: float) -> None:
        """Create a new :class:`Cache` instance.

        Parameters:
            lifetime:
                Lifetime of cached entries in seconds.
        """
        self.entries: dict[Any, dict[str, Any]] = {}
        self.lifetime = lifetime

    def __repr__(self) -> str:
        return str(self.entries)

    def clear(self) -> None:
        """Clear all entries."""
        self.entries.clear()

    def evict_expired(self) -> None:
        """Evict expired entries."""
        now = time.time()
        expired = [
            k for k, v in self.entries.items()
            if (v["timestamp"] + self.lifetime) < now
        ]
        for key in expired:
            self.entries.pop(key)

    def evict(self, key: Any) -> None:
        """Evict a specific entry at the given key."""
        if key in self.entries:
            self.entries.pop(key)

    def add(self, key: Any, data: Any) -> None:
        """Add an entry under a given key."""
        self.evict_expired()
        self.entries[key] = dict(data=data, timestamp=time.time())

    def get(self, key: Any) -> dict[str, Any] | None:
        """Get an entry at the given key. Will return `None` if not found."""
        if not (info := self.entries.get(key)):
            return None
        if (info["timestamp"] + self.lifetime) < time.time():
            self.entries.pop(key)
            return None
        return info["data"]


def freeze(value: Any) -> Any:
    """Make a mutable value immutable."""
    if isinstance(value, Mapping):
        return tuple(sorted((k, freeze(v)) for k, v in value.items()))
    if isinstance(value, list):
        return tuple(freeze(v) for v in value)
    if isinstance(value, set):
        return frozenset(freeze(v) for v in value)
    return value


def generate_key(**kwargs: Any) -> Any:
    """Generate an immutable cache key from keyword-arguments."""
    return freeze(kwargs)
