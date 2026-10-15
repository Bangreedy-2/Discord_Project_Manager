"""A small fake of the discord.py guild API surface the services use."""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any

import discord

from bot.domain.models import ChannelKind

_ids = itertools.count(1000)
_MISSING = object()


class Boom(Exception):
    """Raised by a fake when a test asks for a failure."""


@dataclass(eq=False)
class Role:
    guild: Guild
    id: int
    name: str

    def __hash__(self):
        return hash(self.id)

    def is_default(self) -> bool:
        return self.id == self.guild.id

    @property
    def members(self) -> list[Member]:
        return [m for m in self.guild.members if self in m.roles]

    async def delete(self, reason=None):
        if self not in self.guild.roles:
            raise discord.NotFound(_resp(404), "Unknown Role")
        self.guild.roles.remove(self)
        for m in self.guild.members:
            if self in m.roles:
                m.roles.remove(self)


@dataclass(eq=False)
class Channel:
    guild: Guild
    id: int
    name: str
    kind: ChannelKind | str
    category_id: int | None = None
    overwrites: dict = field(default_factory=dict)
    synced: bool = True
    topic: str | None = None

    def __hash__(self):
        return hash(self.id)

    @property
    def mention(self):
        return f"<#{self.id}>"

    @property
    def category(self):
        return self.guild.get_channel(self.category_id) if self.category_id else None

    @property
    def channels(self) -> list[Channel]:
        return [c for c in self.guild.channels if c.category_id == self.id]

    async def delete(self, reason=None):
        if self not in self.guild.channels:
            raise discord.NotFound(_resp(404), "Unknown Channel")
        self.guild.channels.remove(self)

    async def edit(self, *, name=None, topic=None, sync_permissions=False, category=_MISSING,
                   overwrites=None, reason=None):
        if name is not None:
            self.name = name
        if topic is not None:
            self.topic = topic
        if category is not _MISSING:
            self.category_id = category.id if category else None
        if overwrites is not None:
            self.overwrites = dict(overwrites)
        if sync_permissions and self.category:
            self.overwrites = dict(self.category.overwrites)
            self.synced = True

    async def set_permissions(self, target, *, overwrite, reason=None):
        self.overwrites[target] = overwrite
        self.synced = False

    async def _create(self, name, kind):
        self.guild._maybe_fail("create_channel")
        ch = Channel(self.guild, next(_ids), name, kind, self.id, dict(self.overwrites))
        self.guild.channels.append(ch)
        return ch

    async def create_text_channel(self, name, reason=None):
        return await self._create(name, ChannelKind.TEXT)

    async def create_voice_channel(self, name, reason=None):
        return await self._create(name, ChannelKind.VOICE)

    async def create_forum(self, name, reason=None):
        return await self._create(name, ChannelKind.FORUM)


@dataclass(eq=False)
class Member:
    guild: Guild
    id: int
    roles: list = field(default_factory=list)
    admin: bool = False
    bot: bool = False
    display_name: str = "user"

    def __hash__(self):
        return hash(self.id)

    @property
    def mention(self):
        return f"<@{self.id}>"

    @property
    def guild_permissions(self):
        return discord.Permissions(administrator=self.admin)

    async def add_roles(self, *roles, reason=None):
        self.guild._maybe_fail("add_roles")
        for r in roles:
            if r not in self.roles:
                self.roles.append(r)

    async def remove_roles(self, *roles, reason=None):
        for r in roles:
            if r in self.roles:
                self.roles.remove(r)

    async def edit(self, *, roles, reason=None):
        self.guild._maybe_fail("edit_member")
        self.roles = list(roles)


class Guild:
    def __init__(self, gid: int = 1):
        self.id = gid
        self.default_role = Role(self, gid, "@everyone")
        self.roles: list[Role] = [self.default_role]
        self.channels: list[Channel] = []
        self.members: list[Member] = []
        self.me = self.add_member(2, bot=True)
        self.fail_on: set[str] = set()

    def _maybe_fail(self, op: str):
        if op in self.fail_on:
            raise Boom(op)

    def add_member(self, mid: int, **kw) -> Member:
        m = Member(self, mid, **kw)
        self.members.append(m)
        return m

    def get_role(self, rid):
        return next((r for r in self.roles if r.id == rid), None)

    def get_channel(self, cid):
        return next((c for c in self.channels if c.id == cid), None)

    def get_member(self, mid):
        return next((m for m in self.members if m.id == mid), None)

    async def create_role(self, *, name, permissions, mentionable, hoist, reason=None):
        self._maybe_fail("create_role")
        r = Role(self, next(_ids), name)
        self.roles.append(r)
        return r

    async def create_category(self, name, *, overwrites, reason=None):
        self._maybe_fail("create_category")
        c = Channel(self, next(_ids), name, "category", None, dict(overwrites))
        self.channels.append(c)
        return c

    async def create_text_channel(self, name, *, category=None, reason=None):
        c = Channel(self, next(_ids), name, ChannelKind.TEXT, category.id if category else None)
        self.channels.append(c)
        return c


def _resp(status: int):
    class R:
        pass

    r = R()
    r.status = status
    r.reason = "fake"
    return r
