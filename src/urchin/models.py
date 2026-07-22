"""Urchin API response models.

All models are immutable dataclasses.
Unknown fields from the API are preserved in an `extra` dict.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, fields
from typing import (
    Any, TypeVar,
    dataclass_transform, get_args, get_origin, get_type_hints, overload
)


T = TypeVar("T", bound=type)
_BaseClass = TypeVar("_BaseClass", bound="_Base")


@overload
def basedataclass(cls: T, /, **kwargs: bool) -> T: ...
@overload
def basedataclass(cls: None, /, **kwargs: bool) -> Callable[[T], T]: ...
@dataclass_transform(frozen_default=True)
def basedataclass(cls: T = None, /, **kwargs: bool) -> T | Callable[[T], T]:
    kwargs.setdefault("frozen", True)
    kwargs.setdefault("repr", False)
    kwargs.setdefault("slots", True)
    if cls is None:
        return lambda cls: dataclass(**kwargs)(cls)
    return dataclass(**kwargs)(cls)


def basefield(*, name: str = None, **kwargs: Any):
    metadata = dict(kwargs.pop("metadata", {}))
    if name is not None:
        metadata["name"] = name
    return field(metadata=metadata, **kwargs)


@basedataclass
class _Base:
    extra: dict[str, Any]
    """Any additional fields returned by the API."""

    @classmethod
    def from_dict(cls: type[_BaseClass], data: dict[str, Any]) -> _BaseClass:
        type_hints = get_type_hints(cls)
        renamed_fields = {
            f.metadata["name"]: f.name
            for f in fields(cls) if "name" in f.metadata
        }
        known_fields = {
            f.metadata.get("name") or f.name: f
            for f in fields(cls) if f.name != "extra"
        }
        kwargs = {}
        extra = {}
        for key, value in data.items():
            if key not in known_fields:
                extra[key] = value
                continue

            f = known_fields[key]
            real_key = renamed_fields.get(key, key)
            field_type = type_hints[f.name]

            origin = get_origin(field_type)
            args = get_args(field_type)

            if isinstance(field_type, type) and issubclass(field_type, _Base):
                kwargs[real_key] = field_type.from_dict(value)
                continue

            # Handle dicts of Base subclasses
            if origin is dict and args:
                inner_t = args[1]
                if isinstance(inner_t, type) and issubclass(inner_t, _Base):
                    kwargs[real_key] = {
                        k: inner_t.from_dict(v)
                        for k, v in value.items()
                    }
                    continue

            # Handle lists of Base subclasses
            if origin is list and args:
                inner_t = args[0]
                if isinstance(inner_t, type) and issubclass(inner_t, _Base):
                    kwargs[real_key] = [inner_t.from_dict(v) for v in value]
                    continue

            kwargs[real_key] = value

        return cls(extra=extra, **kwargs)

    def __repr__(self) -> str:
        a = []
        for f in fields(self):
            if not f.repr:
                continue
            if f.name == "extra":
                continue
            a.append(f"{f.name}={getattr(self, f.name)!r}")
        if getattr(self, "extra"):
            a.append("extra={...}")
        return f"{type(self).__name__}({', '.join(a)})"

    @property
    def fields(self) -> list[str]:
        """List of all public attributes."""
        return (
            [f.name for f in fields(self) if f.init and f.name != "extra"] +
            ["extra"]
        )


@basedataclass
class PlayerSession(_Base):
    """A session breakdown for a player."""

    uuid: str
    """The player's Minecraft UUID."""
    since: int = basefield(name="from")
    """Unix millisecond timestamp marking the start of the session."""
    since_readable: str = basefield(name="from_readable")
    """:data:`since` translated into a human-readable string."""
    delta: dict[str, Any] = basefield(repr=False, default_factory=dict)
    """Delta of player statistics since start of session."""


@basedataclass
class Marker(_Base):
    """A single session marker."""

    id: int
    """The numeric ID assigned to this marker."""
    name: str
    """The name assigned to this marker."""
    created_at: int
    """Unix millisecond timestamp marking the creation of the marker."""
    created_readable: str
    """:data:`created_at` translated into a human-readable string."""
    snapshot_timestamp: int
    """Unix millisecond timestamp marking the start of the session."""
    snapshot_readable: str
    """:data:`snapshot_timestamp` translated into a human-readable string."""


@basedataclass
class Snapshot(_Base):
    """A single snapshot."""

    timestamp: int
    """Unix millisecond timestamp marking the snapshot time."""
    readable: str
    """:data:`timestamp` translated into a human-readable string."""


@basedataclass
class PlayerSnapshot(_Base):
    """A snapshot of the player's statistics at a given time."""

    uuid: str
    """The player's Minecraft UUID."""
    timestamp: int
    """Unix millisecond timestamp marking the snapshot time."""
    readable: str
    """:data:`timestamp` translated into a human-readable string."""
    data: dict[str, Any] = basefield(repr=False)
    """Snapshot of player statistics."""


@basedataclass
class Tag(_Base):
    """A single tag applied to a player."""

    tag_type: str
    """The type of tag."""
    reason: str
    """Human-readable reason provided by the tagger."""
    added_on: int
    """Unix millisecond timestamp of when the tag was created."""
    added_by: int | None = None
    """Discord user ID of the tagger, if public."""
    added_by_username: str | None = None
    """Discord username of the tagger, if public."""
    hide_username: bool = False
    """Whether the tagger requested their username to be hidden."""


@basedataclass
class Winstreak(_Base):
    """A single winstreak estimation."""

    value: int
    """The estimated winstreak value."""
    approximate: bool
    """Whether the estimate is approximated."""
    timestamp: int
    """Unix millisecond timestamp of when the winstreak was estimated."""
    readable: str
    """:data:`timestamp` translated into a human-readable string."""


@basedataclass
class GuildExp(_Base):
    """Guild experience earned for a guild."""

    total: int = basefield(name="exp")
    """Total guild experience."""
    by_game: dict[str, int] = basefield(name="guildExpByGameType")
    """Breakdown of guild experience for each game type."""


@basedataclass
class GuildMemberExp(_Base):
    """Guild experience earned by a guild member."""

    total: int = basefield(default=0)
    """Total guild experience earned."""
    daily: dict[str, int] = basefield(default_factory=dict)
    """Breakdown of daily experience."""


@basedataclass
class GuildMember(_Base):
    """A guild member's experience and quest participation."""

    gexp: GuildMemberExp
    """Guild experience earned by this member."""
    quest_participation: int = basefield(name="questParticipation", default=0)
    """The quest participation of this member."""


@basedataclass
class GuildSession(_Base):
    """A session breakdown for a guild."""

    guild_id: str
    """The ID of the guild."""
    name: str
    """The name of the guild."""
    since: int = basefield(name="from")
    """Unix millisecond timestamp marking the start of the session."""
    since_readable: str = basefield(name="from_readable")
    """:data:`since` translated into a human-readable string."""
    gexp: GuildExp = basefield(name="guild")
    """Guild experience earned this session."""
    members: dict[str, GuildMember] = basefield(repr=False)
    """Mapping of member UUIDs to their experience and quest participation."""


@basedataclass
class GuildSnapshot(_Base):
    """A snapshot of a guild's Hypixel API endpoint at a given time."""

    guild_id: str
    """The ID of the guild."""
    timestamp: int
    """Unix millisecond timestamp marking the snapshot time."""
    readable: str
    """:data:`timestamp` translated into a human-readable string."""
    data: dict[str, Any] = basefield(repr=False)
    """Snapshot of Hypixel API endpoint."""
