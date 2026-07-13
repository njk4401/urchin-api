"""Urchin API client.

Minimal usage::

    async with UrchinClient(api_key="YOUR_KEY") as client:
        tags = await client.get_tags("PlayerName")
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, TypeVar, overload

import aiohttp

from .cache import Cache, generate_key
from .exceptions import NotFoundError
from .http import request
from .models import (
    GuildSession, GuildSnapshot, Marker, PlayerSession,
    PlayerSnapshot, Snapshot, Tag
)


T = TypeVar("T")


class UrchinClient:
    """Asynchronous client for the Urchin (Coral) REST API.

    All API GET methods are transparently cached so that repeated
    identical requests within a short window do not spam the network.

    These cached entries can be cleared by calling :attr:`cache`.clear.

    Examples
    --------
    As an async context manager (recommended)::

        async with UrchinClient(api_key="YOUR_KEY") as client:
            ...

    Manual lifecycle::

        client = UrchinClient(api_key="YOUR_KEY")
        await client.connect()
        try:
            ...
        finally:
            await client.close()
    """
    def __init__(self, *,
        api_key: str,
        base_url: str = "https://api.urchin.gg/v3",
        max_retries: int = 3,
        backoff_base: float = 0.5,
        cache_lifetime: float = 300,
        session: aiohttp.ClientSession = None
    ) -> None:
        """Create a new :class:`UrchinClient` instance.

        Parameters:
            api_key:
                An Urchin API key, obtained via `/dashboard`
                through the official Urchin Discord bot.
                The key can be changed after construction by
                assigning to :attr:`api_key`.
            base_url:
                Root URL for the Urchin REST API.
                Override this to point at a staging environment or local proxy.
            max_retries:
                Number of times to retry a failed request
                before raising an exception.
            backoff_base:
                Seconds to wait before the first failed request is retried.
                Each subsequent retry will double this value.
            cache_lifetime:
                The duration that successful API calls are cached in seconds.
                Cached entries can be cleared by calling :attr:`cache`.clear.
            session:
                An existing :class:`aiohttp.ClientSession` to reuse.
                If provided, the responsibility for closing the session
                falls upon the caller; the client will **NOT**
                close the session on :meth:`close` or
                after losing scope of `async with`.
        """
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.cache = Cache(cache_lifetime)
        self._session = session
        self._owns_session = session is None

    #==========================================================================
    # Lifecycle
    #==========================================================================
    async def __aenter__(self) -> UrchinClient:
        await self.connect()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    async def connect(self) -> None:
        """Open the underlying HTTP client session.

        Calling this explicitly is never necessary
        when using the client as an async context manager.
        """
        await self._get_session()

    async def close(self) -> None:
        """Close the underlying HTTP client session.

        Only closes if the client owns the session.
        If a custom session was passed at construction time, it is left open.
        """
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()

    #==========================================================================
    # Properties
    #==========================================================================
    @property
    def api_key(self) -> str:
        """The API key used to authenticate requests.

        Assigning a new value takes effect immediately.
        """
        return self._api_key

    @api_key.setter
    def api_key(self, value: str) -> None:
        self._api_key = value

    #==========================================================================
    # Internal Helpers
    #==========================================================================
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get the active HTTP session, creating one if necessary."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"Accept": "application/json"}
            )
        return self._session

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self._base_url}/{path.lstrip('/')}"
        session = await self._get_session()
        kwargs.setdefault("headers", {})["X-API-Key"] = self.api_key
        data = await request(
            session, method, url,
            max_retries=kwargs.pop("max_retries", self.max_retries),
            backoff_base=kwargs.pop("backoff_base", self.backoff_base),
            **kwargs
        )
        return data

    async def _get(self, path: str, **kwargs: Any) -> Any:
        key = generate_key(path=path, **kwargs)
        if (data := self.cache.get(key)) is not None:
            return data
        data = await self._request("GET", path, **kwargs)
        self.cache.add(key, data)
        return data

    async def _post(self, path: str, **kwargs: Any) -> Any:
        return await self._request("POST", path, **kwargs)

    async def _delete(self, path: str, **kwargs: Any) -> Any:
        return await self._request("DELETE", path, **kwargs)

    async def _patch(self, path: str, **kwargs: Any) -> Any:
        return await self._request("PATCH", path, **kwargs)

    #==========================================================================
    # Player Sessions
    #==========================================================================
    @overload
    async def get_session(self,
        player: str,
        *,
        duration: str
    ) -> PlayerSession: ...
    @overload
    async def get_session(self,
        player: str,
        *,
        since: int | str
    ) -> PlayerSession: ...
    @overload
    async def get_session(self,
        player: str,
        *,
        marker: str
    ) -> PlayerSession: ...
    async def get_session(self,
        player: str,
        *,
        duration: str = None,
        since: int | str = None,
        marker: str = None
    ) -> PlayerSession:
        """Fetch the change in a player's statistics over a defined window.

        Must supply **exactly one** of the three keyword arguments
        that define the start of the session window.

        Parameters:
            player:
                The player's username or UUID.
            duration:
                Lookback window as a duration string.
                e.g. `"48h"`, `"10d"`, `"2w"`
            since:
                Absolute start of the session as either
                a Unix millisecond timestamp or a RFC 3339 string.
            marker:
                Name of a saved marker that defines the start of the session.
                Requires that :attr:`api_key` is linked to `player`
                or that it holds the `All Sessions` access level.
        """
        p = {
            k: v for k, v in (
                ("player", player),
                ("duration", duration or None),
                ("from", since or None),
                ("marker", marker or None)
            ) if v is not None
        }
        if len(p) != 2:
            raise ValueError(
                "must provide exactly one of duration, since, or marker"
            )

        data = await self._get("player/sessions/custom", params=p)
        return PlayerSession.from_dict(data)

    async def get_markers(self, player: str) -> list[Marker]:
        """Fetch all session markers saved for a player.

        Markers are named reference points in time attached to a player's
        account. They can be passed to :meth:`get_session` to measure stat
        changes since a specific moment.

        Requires that :attr:`api_key` is linked to `player`
        or that it holds the `All Sessions` access level.

        Parameters:
            player:
                The player's username or UUID.
        """
        p = {"player": player}
        data = await self._get("player/sessions/markers", params=p)
        return [Marker.from_dict(m) for m in data.get("markers", [])]

    async def create_marker(self, player: str, name: str = None) -> Marker:
        """Create a session marker for a player pinned to the current snapshot.

        A marker records the player's stat snapshot at the moment it is
        created. It can later be passed to :meth:`get_session` to measure
        stat changes since a specific moment.

        Requires that :attr:`api_key` is linked to `player`
        or that it holds the `All Sessions` access level.

        Parameters:
            player:
                The player's username or UUID.
            name:
                A label assigned to the marker, limited to 32 characters.
                If not provided, will default to today's date.
        """
        p = {"player": player}
        j = {"name": name[:32]} if name else {}
        data = await self._post("player/sessions/markers", params=p, json=j)
        return Marker.from_dict(data)

    async def delete_marker(self, player: str, name: str) -> bool:
        """Attempt to permanently delete a session marker for a player.

        ### ***Warning***
            **There is no confirmation nor a way to recover a deleted marker.**

        Requires that :attr:`api_key` is linked to `player`
        or that it holds the `All Sessions` access level.

        Parameters:
            player:
                The player's username or UUID.
            name:
                The name of the marker to delete.

        Returns:
            bool:
                `True` if the marker was found and successfully deleted,
                otherwise `False`.
        """
        p = {"player": player}
        try:
            data = await self._delete(
                f"player/sessions/markers/{name[:32]}", params=p
            )
        except NotFoundError:
            return False
        return data.get("success", False)

    async def rename_marker(self,
        player: str,
        name: str,
        new_name: str
    ) -> bool:
        """Attempt to rename a session marker for a player.

        Requires that :attr:`api_key` is linked to `player`
        or that it holds the `All Sessions` access level.

        Parameters:
            player:
                The player's username or UUID.
            name:
                The current name of the marker to rename.
            new_name:
                The desired name for the marker, limited to 32 characters.

        Returns:
            bool:
                `True` if the marker was found and successfully renamed,
                otherwise `False`.
        """
        p = {"player": player}
        j = {"new_name": new_name[:32]}
        try:
            data = await self._patch(
                f"player/sessions/markers/{name[:32]}", params=p, json=j
            )
        except NotFoundError:
            return False
        return data.get("success", False)

    async def get_snapshots(self,
        player: str,
        *,
        before: int | str = None,
        after: int | str = None
    ) -> list[Snapshot]:
        """Fetch the timestamps of all snapshots recorded for a player.

        Use this to discover what points in time are available before calling
        :meth:`get_snapshot` in order to fetch the most accurate data.

        Requires that :attr:`api_key` is linked to `player`
        or that it holds the `All Sessions` access level.

        Parameters:
            player:
                The player's username or UUID.
            before:
                Exclude snapshots recorded at or after this time.
                Either a Unix millisecond timestamp or a RFC 3339 string.
            after:
                Exclude snapshots recorded before this time.
                Either a Unix millisecond timestamp or a RFC 3339 string.
        """
        p = {
            k: v for k, v in (
                ("player", player),
                ("before", before or None),
                ("after", after or None)
            ) if v is not None
        }
        data = await self._get("player/sessions/snapshots", params=p)
        return [Snapshot.from_dict(d) for d in data.get("snapshots", [])]

    async def get_snapshot(self, player: str, at: int | str) -> PlayerSnapshot:
        """Fetch a player's full statistics snapshot at a given timestamp.

        Requires that :attr:`api_key` is linked to `player`
        or that it holds the `All Sessions` access level.

        Parameters:
            player:
                The player's username or UUID.
            at:
                The timestamp of the desired snapshot as either
                a Unix millisecond timestamp or a RFC 3339 string.
                If no snapshot exists at the exact time given,
                will return either the nearest rounded down,
                or the earliest.
        """
        p = {"player": player, "at": at}
        data = await self._get("player/sessions/snapshots", params=p)
        return PlayerSnapshot.from_dict(data)

    #==========================================================================
    # Blacklist
    #==========================================================================
    async def get_tags(self, player: str) -> list[Tag]:
        """Fetch the active blacklist tags applied to a player.

        Parameters:
            player:
                The player's username or UUID.
        """
        p = {"player": player}
        data = await self._get("player/tags", params=p)
        return [Tag.from_dict(v) for v in data.get("tags")]

    @overload
    async def batch_get_tags(self, *uuids: str) -> dict[str, list[Tag]]: ...
    @overload
    async def batch_get_tags(self,
        uuids: Iterable[str], /
    ) -> dict[str, list[Tag]]: ...
    async def batch_get_tags(self,
        *uuids: str | Iterable[str]
    ) -> dict[str, list[Tag]]:
        """Fetch blacklist tags for multiple players in a single request.

        This method is much more efficient than calling
        :meth:`get_tags` as usernames are not resolved.

        Parameters:
            uuids:
                Either multiple player UUIDs or a single iterable.
                At most 100 will be processed.
                Any malformed entries will be silently dropped.

        Returns:
            dict[str, list[Tag]]:
                A mapping of each UUID which was passed with its associated
                list of tags. UUIDs with no tags are included with
                an empty list. UUIDs which were silently dropped will
                be absent from the mapping.
        """
        if len(uuids) == 1 and not isinstance(uuids[0], str):
            j = {"uuids": list(uuids[0])[:100]}
        else:
            j = {"uuids": list(uuids)[:100]}

        # Response isn't automatically cached since it is a post method
        key = generate_key(path="players", json=j)
        if (data := self.cache.get(key)) is None:
            data = await self._post("players", json=j)
            self.cache.add(key, data)

        return {
            k: [Tag.from_dict(v) for v in val]
            for k, val in data.get("players", {}).items()
        }

    async def blacklist_lock(self, player: str, reason: str) -> None:
        """Apply a moderation lock to a player.

        While a player is locked, all attempts to add, modify,
        or remove tags for them will be rejected until the lock
        is lifted via :meth:`blacklist_unlock`.

        Requires that :attr:`api_key` holds the `Moderator` access level.

        Parameters:
            player:
                The player's username or UUID.
            reason:
                An explanation for why the lock is being applied.
        """
        p = {"player": player}
        j = {"reason": reason}
        await self._post("player/lock", params=p, json=j)

    async def blacklist_unlock(self, player: str) -> None:
        """Lift a moderation lock from a player.

        Once unlocked, tags can be added to or modified
        for the player again as normal.

        Requires that :attr:`api_key` holds the `Moderator` access level.

        Parameters:
            player:
                The player's username or UUID.
        """
        p = {"player": player}
        await self._delete("player/lock", params=p)

    async def add_tag(self,
        player: str,
        tag_type: str,
        reason: str,
        *,
        hide_account: bool = False
    ) -> Tag:
        """Apply a blacklist tag to a player.

        Applied tags are associated with the account linked to :attr:`api_key`.

        Parameters:
            player:
                The player's username or UUID.
            tag_type:
                The tag type to apply.
                The types that can be applied depend
                on the access level of :attr:`api_key`.
            reason:
                An explanation for why this tag is being applied.
            hide_account:
                Request that the tagger's account
                not be associated with the applied tag.
                Whether this is honored depends on the
                access level of :attr:`api_key`.
        """
        p = {"player": player}
        j = {"type": tag_type, "reason": reason, "hide_username": hide_account}
        data = await self._post("tags", params=p, json=j)
        return Tag.from_dict(data)

    async def remove_tag(self, player: str, tag_type: str) -> None:
        """Remove a blacklist tag of the given type from a player.

        Removing a tag created by someone else or
        a tag that was applied before :attr:`api_key` was created,
        requires that :attr:`api_key` holds the appropriate access level.

        Parameters:
            player:
                The player's username or UUID.
            tag_type:
                The type of tag to remove.
        """
        p = {"player": player}
        j = {"type": tag_type}
        await self._delete("tags", params=p, json=j)

    async def modify_tag(self,
        player: str,
        tag_type: str,
        new_reason: str,
        new_type: str = None,
        *,
        hide_account: bool = False
    ) -> Tag:
        """Modify an active blacklist tag applied to a player.

        The `confirmed_cheater` type cannot be set through this endpoint.

        Parameters:
            player:
                The player's username or UUID.
            tag_type:
                The tag type to modify.
            new_reason:
                The updated explanation that will replace the existing one.
            new_type:
                If provided, the tag's type is changed to this value.
                Defaults to the tag's existing type.
            hide_account:
                Request that the tagger's account
                not be associated with the updated tag.
                Whether this is honored depends on the
                access level of :attr:`api_key`.
        """
        p = {"player": player}
        j = {
            "type": tag_type, "hide_username": hide_account,
            "new_reason": new_reason, "new_type": new_type or tag_type
        }
        data = await self._patch("tags", params=p, json=j)
        return Tag.from_dict(data)

    #==========================================================================
    # Guild Sessions
    #==========================================================================
    @overload
    async def get_guild_session(self,
        guild: str,
        *,
        duration: str
    ) -> GuildSession: ...
    @overload
    async def get_guild_session(self,
        guild: str,
        *,
        since: int | str
    ) -> GuildSession: ...
    async def get_guild_session(self,
        guild: str,
        *,
        duration: str = None,
        since: int | str = None,
    ) -> GuildSession:
        """Fetch the change in a guild over a defined window.

        Must supply **exactly one** of the keyword arguments
        that define the start of the session window.

        Requires that :attr:`api_key` is linked to a player in `guild`.

        Parameters:
            guild:
                The guild's name or ID.
            duration:
                Lookback window as a duration string.
                e.g. `"48h"`, `"10d"`, `"2w"`
            since:
                Absolute start of the session as either
                a Unix millisecond timestamp or a RFC 3339 string.
        """
        p = {
            k: v for k, v in (
                ("guild", guild),
                ("duration", duration or None),
                ("from", since or None)
            ) if v is not None
        }
        if len(p) != 2:
            msg = "must provide exactly one of duration or since"
            raise ValueError(msg)

        data = await self._get("guild/sessions/custom", params=p)
        return GuildSession.from_dict(data)

    async def get_guild_snapshot(self,
        guild: str,
        at: int | str
    ) -> GuildSnapshot:
        """Fetch a guild's snapshot at a given timestamp.

        Requires that :attr:`api_key` is linked to a player in `guild`.

        Parameters:
            guild:
                The guild's name or ID.
            at:
                The timestamp of the desired snapshot as either
                a Unix millisecond timestamp or a RFC 3339 string.
                If no snapshot exists at the exact time given,
                will return either the nearest rounded down,
                or the earliest.
        """
        p = {"guild": guild, "at": at}
        data = await self._get("guild/sessions/snapshots", params=p)
        return GuildSnapshot.from_dict(data)

    async def get_guild_snapshots(self,
        guild: str,
        *,
        before: int | str = None,
        after: int | str = None
    ) -> list[Snapshot]:
        """Fetch the timestamps of all snapshots recorded for a player.

        Use this to discover what points in time are available before calling
        :meth:`get_guild_snapshot` in order to fetch the most accurate data.

        Requires that :attr:`api_key` is linked to a player in `guild`.

        Parameters:
            guild:
                The guild's name or ID.
            before:
                Exclude snapshots recorded at or after this time.
                Either a Unix millisecond timestamp or a RFC 3339 string.
            after:
                Exclude snapshots recorded before this time.
                Either a Unix millisecond timestamp or a RFC 3339 string.
        """
        p = {
            k: v for k, v in (
                ("guild", guild),
                ("before", before or None),
                ("after", after or None)
            ) if v is not None
        }
        data = await self._get("guild/sessions/snapshots", params=p)
        return [Snapshot.from_dict(d) for d in data.get("snapshots", [])]
