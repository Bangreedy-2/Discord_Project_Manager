"""In-memory implementations of the repositories, mirroring the SQL semantics we rely on."""

from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

from bot.db.repos import Repos
from bot.domain.models import (
    AuditEntry, GuildSettings, Project, ProjectChannel, ProjectStatus,
)
from bot.errors import CapReached, DuplicateName

LIVE = (ProjectStatus.PENDING, ProjectStatus.ACTIVE, ProjectStatus.BROKEN)


class MemProjects:
    def __init__(self, store):
        self.s = store
        self.rows: dict = {}

    async def reserve(self, guild_id, creator_id, name, bypass):
        cap = (await self.s.settings.get(guild_id)).max_projects_per_user
        if not bypass and await self.count_for_creator(guild_id, creator_id) >= cap:
            raise CapReached()
        if any(p.guild_id == guild_id and p.name.lower() == name.lower()
               and p.status is not ProjectStatus.DELETING for p in self.rows.values()):
            raise DuplicateName(name)
        p = Project(uuid4(), guild_id, name, creator_id, ProjectStatus.PENDING,
                    None, None, None, None, datetime.now(timezone.utc))
        self.rows[p.id] = p
        return p.id

    async def activate(self, pid, cat, o, m, v):
        self.rows[pid] = replace(self.rows[pid], category_id=cat, owner_role_id=o,
                                 member_role_id=m, viewer_role_id=v,
                                 status=ProjectStatus.ACTIVE)

    async def set_status(self, pid, status):
        self.rows[pid] = replace(self.rows[pid], status=status)

    async def update_ids(self, pid, **ids):
        self.rows[pid] = replace(self.rows[pid], **ids)

    async def delete(self, pid):
        self.rows.pop(pid, None)
        for cid in [c for c, ch in self.s.channels.rows.items() if ch.project_id == pid]:
            del self.s.channels.rows[cid]

    async def get(self, pid):
        return self.rows.get(pid)

    async def get_by_name(self, guild_id, name):
        return next((p for p in self.rows.values() if p.guild_id == guild_id
                     and p.name.lower() == name.lower()
                     and p.status is not ProjectStatus.DELETING), None)

    async def get_by_category(self, cat):
        return next((p for p in self.rows.values() if p.category_id == cat), None)

    async def get_by_role(self, role_id):
        return next((p for p in self.rows.values() if role_id in p.role_ids), None)

    async def list_for_guild(self, guild_id, statuses=(ProjectStatus.ACTIVE,)):
        return sorted((p for p in self.rows.values()
                       if p.guild_id == guild_id and p.status in statuses),
                      key=lambda p: p.name.lower())

    async def list_for_owner(self, guild_id, role_ids):
        return [p for p in await self.list_for_guild(
            guild_id, (ProjectStatus.ACTIVE, ProjectStatus.BROKEN))
            if p.owner_role_id in role_ids]

    async def count_for_creator(self, guild_id, creator_id):
        return sum(1 for p in self.rows.values() if p.guild_id == guild_id
                   and p.creator_id == creator_id and p.status in LIVE)

    async def list_stale_pending(self, older_than_minutes=10):
        return [p for p in self.rows.values() if p.status is ProjectStatus.PENDING]


class MemChannels:
    def __init__(self):
        self.rows: dict = {}

    async def add(self, channel_id, project_id, kind, created_by):
        self.rows.setdefault(channel_id, ProjectChannel(
            channel_id, project_id, kind, False, False, created_by, datetime.now(timezone.utc)))

    async def remove(self, channel_id):
        self.rows.pop(channel_id, None)

    async def get(self, channel_id):
        return self.rows.get(channel_id)

    async def list_for_project(self, pid):
        return [c for c in self.rows.values() if c.project_id == pid]

    async def count_for_project(self, pid):
        return len(await self.list_for_project(pid))

    async def set_public(self, channel_id, is_public):
        self.rows[channel_id] = replace(self.rows[channel_id], is_public=is_public)


class MemSettings:
    def __init__(self):
        self.rows: dict = {}

    async def get(self, guild_id):
        return self.rows.get(guild_id, GuildSettings(guild_id))

    async def update(self, guild_id, max_projects_per_user=None, max_channels_per_proj=None):
        cur = await self.get(guild_id)
        self.rows[guild_id] = GuildSettings(
            guild_id,
            max_projects_per_user if max_projects_per_user is not None else cur.max_projects_per_user,
            max_channels_per_proj if max_channels_per_proj is not None else cur.max_channels_per_proj,
        )
        return self.rows[guild_id]


class MemAudit:
    def __init__(self):
        self.entries: list[AuditEntry] = []

    async def write(self, entry):
        self.entries.append(entry)

    @property
    def actions(self):
        return [e.action for e in self.entries]


def memory_repos() -> Repos:
    class _S:
        pass

    s = _S()
    s.settings = MemSettings()
    s.channels = MemChannels()
    projects = MemProjects(s)
    return Repos(projects=projects, channels=s.channels, settings=s.settings, audit=MemAudit())
