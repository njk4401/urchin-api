"""Python client for the Urchin (Coral) API.

Quickstart::
    import asyncio
    from urchin import UrchinClient

    async def main() -> None:
        async with UrchinClient(api_key="YOUR_KEY") as client:
            tags = await client.get_tags("PlayerName")

    asyncio.run(main())
"""

from .client import UrchinClient
from .exceptions import (
    AuthError, NotFoundError, RateLimitError, ServerError, UrchinError
)
from .models import (
    GuildSession, GuildSnapshot, Marker, PlayerSession,
    PlayerSnapshot, Snapshot, Tag, Winstreak
)


__version__ = "0.2.0"

__all__ = (
    "UrchinClient",
    "UrchinError",
    "AuthError",
    "NotFoundError",
    "RateLimitError",
    "ServerError",
    "Marker",
    "Snapshot",
    "Tag",
    "Winstreak",
    "PlayerSession",
    "PlayerSnapshot",
    "GuildSession",
    "GuildSnapshot"
)
