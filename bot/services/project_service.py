"""Project lifecycle: create (saga with compensation), delete, lookups."""

import logging
from dataclasses import dataclass
from typing import Any

import discord

from bot.db.repos import Repos
from bot.domain import overwrites
from bot.domain.models import AuditEntry, ChannelKind, Project, ProjectChannel, ProjectStatus, Tier
from bot.errors import ProjectNotFound, RoleSlotsExhausted
from bot.services import authz
from bot.services.discord_utils import safe_delete

log = logging.getLogger(__name__)

MAX_GUILD_ROLES = 250
ROLES_PER_PROJECT = 3


def remaining_project_slots(guild: Any) -> int:
    return max(0, (MAX_GUILD_ROLES - len(guild.roles)) // ROLES_PER_PROJECT)


@dataclass
class ProjectInfo:
    project: Project
    owners: list[Any]
    members: list[Any]
    viewers: list[Any]
    channels: list[tuple[ProjectChannel, Any]]


class ProjectService:
    def __init__(self, repos: Repos):
        self.repos = repos

    async def resolve(self, guild_id: int, name: str) -> Project:
        project = await self.repos.projects.get_by_name(guild_id, name)
        if project is None or project.status not in (ProjectStatus.ACTIVE, ProjectStatus.BROKEN):
            raise ProjectNotFound(name)
        return project

    async def resolve_by_category(self, category_id: int | None) -> Project | None:
        if category_id is None:
            return None
        project = await self.repos.projects.get_by_category(category_id)
        if project is None or project.status not in (ProjectStatus.ACTIVE, ProjectStatus.BROKEN):
            return None
        return project

    async def create(self, guild: Any, actor: Any, raw_name: str) -> Project:
        name = overwrites.validate_project_name(raw_name)
        if remaining_project_slots(guild) < 1:
            raise RoleSlotsExhausted()

        project_id = await self.repos.projects.reserve(
            guild.id, actor.id, name, bypass=authz.is_admin(actor)
        )
        created: list[Any] = []
        reason = f"Project {name} created by {actor}"
        try:
            roles = {}
            for tier in (Tier.OWNER, Tier.MEMBER, Tier.VIEWER):
                role = await guild.create_role(
                    name=overwrites.role_name(name, tier),
                    permissions=discord.Permissions.none(),
                    mentionable=False,
                    hoist=False,
                    reason=reason,
                )
                created.append(role)
                roles[tier] = role

            category = await guild.create_category(
                name,
                overwrites=overwrites.category_overwrites(
                    guild, roles[Tier.OWNER], roles[Tier.MEMBER], roles[Tier.VIEWER]
                ),
                reason=reason,
            )
            created.append(category)

            general = await category.create_text_channel("general", reason=reason)
            created.append(general)
            await self.repos.channels.add(general.id, project_id, ChannelKind.TEXT, actor.id)

            await actor.add_roles(roles[Tier.OWNER], reason=reason)

            await self.repos.projects.activate(
                project_id,
                category.id,
                roles[Tier.OWNER].id,
                roles[Tier.MEMBER].id,
                roles[Tier.VIEWER].id,
            )
        except BaseException:
            log.exception("project create failed, rolling back %s", name)
            for obj in reversed(created):
                await safe_delete(obj, reason=f"Rolling back failed creation of {name}")
            try:
                await self.repos.projects.delete(project_id)
            except Exception:
                log.exception("failed to delete reserved row %s", project_id)
            raise

        await self.repos.audit.write(
            AuditEntry(guild.id, actor.id, "project.create", project_id, category.id, {"name": name})
        )
        project = await self.repos.projects.get(project_id)
        assert project is not None
        return project

    async def delete(self, guild: Any, actor: Any, project: Project) -> None:
        authz.require_creator_or_admin(project, actor)
        await self.repos.projects.set_status(project.id, ProjectStatus.DELETING)
        reason = f"Project {project.name} deleted by {actor}"

        category = guild.get_channel(project.category_id) if project.category_id else None
        tracked = await self.repos.channels.list_for_project(project.id)
        channel_ids = {c.channel_id for c in tracked}
        if category is not None:
            channel_ids |= {c.id for c in category.channels}
        for channel_id in channel_ids:
            await safe_delete(guild.get_channel(channel_id), reason=reason)
        await safe_delete(category, reason=reason)
        for role_id in project.role_ids:
            await safe_delete(guild.get_role(role_id), reason=reason)

        await self.repos.audit.write(
            AuditEntry(
                guild.id, actor.id, "project.delete", project.id, project.category_id,
                {"name": project.name},
            )
        )
        await self.repos.projects.delete(project.id)

    async def info(self, guild: Any, project: Project) -> ProjectInfo:
        def holders(role_id: int | None) -> list[Any]:
            role = guild.get_role(role_id) if role_id else None
            return list(role.members) if role else []

        channels = [
            (c, guild.get_channel(c.channel_id))
            for c in await self.repos.channels.list_for_project(project.id)
        ]
        return ProjectInfo(
            project=project,
            owners=holders(project.owner_role_id),
            members=holders(project.member_role_id),
            viewers=holders(project.viewer_role_id),
            channels=channels,
        )

    async def list_owned(self, guild: Any, member: Any) -> list[Project]:
        if authz.is_admin(member):
            return await self.repos.projects.list_for_guild(
                guild.id, (ProjectStatus.ACTIVE, ProjectStatus.BROKEN)
            )
        return await self.repos.projects.list_for_owner(guild.id, [r.id for r in member.roles])
