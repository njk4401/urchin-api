# urchin-api

Unofficial async Python client for the **Urchin (Coral) API** - a community-maintained
player blacklist and stat tracking service for Hypixel.

## Installation

```bash
pip install urchin-api
```

Requires **Python 3.10+**.

## Getting an API key

Use the `/dashboard` command in the official [Urchin Discord](https://discord.gg/urchin).

## Usage

```python
import asyncio
from urchin import UrchinClient

async def main():
    async with UrchinClient(api_key="YOUR_KEY") as client:

        # Single player tag lookup
        tags = await client.get_tags("PlayerName")
        for tag in tags:
            print(f"[{tag.tag_type}] {tag.reason}")

        # Session stats
        stats = await client.get_session("PlayerName", duration="24h")
        if stats.delta:
            print(f"Changes since {stats.since_readable} - {stats.delta}")

        # Batch tag lookup
        lobby = await client.batch_get_tags("UUID1", "UUID2", "UUID3")
        for uuid, tags in lobby.items():
            if tags:
                print(f"⚠ {uuid} is tagged - {tags[0].tag_type}!")

asyncio.run(main())
```

### Exceptions

| Exception | When |
|---|---|
| `AuthError` | Invalid or missing API key (401/403) |
| `NotFoundError` | Player or resource not found (404) |
| `RateLimitError` | Too many requests (429) — has `.retry_after` |
| `ServerError` | Server-side failure (5xx) — has `.status` |
| `UrchinError` | Base class for all of the above |

## License

MIT
