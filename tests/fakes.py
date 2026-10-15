"""Minimal stand-ins for discord objects used by the pure and service-level tests."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

import discord

from bot.domain.models import Project, ProjectStatus


@dataclass(eq=False)
class FakeRole:
    id: int
    name: str = "role"

    def __hash__(self) -> int:
        return hash(self.id)


@dataclass(eq=False)
class FakeMember:
    id: int
    roles: list = field(default_factory=list)
    admin: bool = False
    bot: bool = False

    @property
    def guild_permissions(self) -> discord.Permissions:
        return discord.Permissions(administrator=self.admin)


@dataclass
class FakeChannel:
    id: int
    category_id: int | None = None


@dataclass
class FakeGuild:
    default_role: FakeRole = field(default_factory=lambda: FakeRole(1, "@everyone"))
    me: FakeMember = field(default_factory=lambda: FakeMember(2, bot=True))


def make_project(**kw) -> Project:
    defaults = dict(
        id=uuid4(), guild_id=1, name="Apollo", creator_id=10,
        status=ProjectStatus.ACTIVE, category_id=100,
        owner_role_id=101, member_role_id=102, viewer_role_id=103,
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(kw)
    return Project(**defaults)
