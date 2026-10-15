"""Drift detection and repair: keeps Discord in line with what Supabase says should exist."""

import logging
from dataclasses import dataclass, field
from typing import Any

import discord

from bot.db.repos import Repos
from bot.domain import overwrites
from bot.domain.models import AuditEntry, ChannelKind, Project, ProjectStatus, Tier
from bot.services.channel_service import kind_of
from bot.services.discord_utils import safe_delete

log = logging.getLogger(__name__)

REPAIRABLE = (ProjectStatus.ACTIVE, ProjectStatus.BROKEN)


@dataclass
class RepairReport:
    project: str
    fixed: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.fixed)


def _same_overwrite(a: Any, b: discord.PermissionOverwrite) -> bool:
    return a is not None and a.pair() == b.pair()


class ReconcileService:
    def __init__(self, repos: Repos):
        self.repos = repos

    async def _audit(self, guild: Any, project: Project, action: str, **details: Any) -> None:
        actor = guild.me.id if guild.me else 0
        await self.repos.audit.write(AuditEntry(guild.id, actor, action, project.id, None, details))

    async def repair(self, guild: Any, project: Project) -> RepairReport:
        """Recreate missing roles/category, re-track channels and restore public overwrites."""
        report = RepairReport(project.name)
        if project.status not in REPAIRABLE:
            return report
        try:
            await self._repair(guild, project, report)
        except discord.HTTPException as e:
            log.exception("repair of %s failed", project.name)
            report.problems.append(f"Discord refused a repair step: {e}")
        if report.problems:
            await self.repos.projects.set_status(project.id, ProjectStatus.BROKEN)
        elif project.status is ProjectStatus.BROKEN or report.changed:
            await self.repos.projects.set_status(project.id, ProjectStatus.ACTIVE)
        if report.changed or report.problems:
            await self._audit(guild, project, "project.repair",
                              fixed=report.fixed, problems=report.problems)
        return report

    async def _repair(self, guild: Any, project: Project, report: RepairReport) -> None:
        reason = f"Repairing project {project.name}"

        # 1. Roles
        roles: dict[Tier, Any] = {}
        recreated_roles = False
        for tier in Tier:
            role = guild.get_role(project.role_id(tier)) if project.role_id(tier) else None
            if role is None:
                role = await guild.create_role(
                    name=overwrites.role_name(project.name, tier),
                    permissions=discord.Permissions.none(),
                    mentionable=False, hoist=False, reason=reason,
                )
                await self.repos.projects.update_ids(project.id, **{f"{tier.value}_role_id": role.id})
                report.fixed.append(f"recreated the {tier.value} role")
                recreated_roles = True
            roles[tier] = role

        wanted = overwrites.category_overwrites(
            guild, roles[Tier.OWNER], roles[Tier.MEMBER], roles[Tier.VIEWER]
        )

        # 2. Category
        category = guild.get_channel(project.category_id) if project.category_id else None
        recreated_category = False
        if category is None:
            category = await guild.create_category(project.name, overwrites=wanted, reason=reason)
            await self.repos.projects.update_ids(project.id, category_id=category.id)
            report.fixed.append("recreated the category")
            recreated_category = True
        elif recreated_roles:
            await category.edit(overwrites=wanted, reason=reason)
            report.fixed.append("restored the category permissions")

        # 3. Tracked channels: drop missing ones, pull strays back into the category
        tracked = {c.channel_id: c for c in await self.repos.channels.list_for_project(project.id)}
        for channel_id, row in list(tracked.items()):
            channel = guild.get_channel(channel_id)
            if channel is None:
                await self.repos.channels.remove(channel_id)
                del tracked[channel_id]
                report.fixed.append(f"stopped tracking deleted channel {channel_id}")
            elif channel.category_id != category.id:
                await channel.edit(category=category, sync_permissions=not row.is_public,
                                   reason=reason)
                report.fixed.append(f"moved #{channel.name} back into the category")

        # 4. Untracked channels inside the category (created by hand)
        for channel in category.channels:
            if channel.id not in tracked:
                kind = kind_of(channel) or ChannelKind.TEXT
                await self.repos.channels.add(channel.id, project.id, kind, guild.me.id)
                report.fixed.append(f"started tracking #{channel.name}")

        # 5. Public channels keep their @everyone overwrite; after role or category
        #    recreation they also need the category's overwrites again.
        everyone_ow_needed = recreated_roles or recreated_category
        for row in await self.repos.channels.list_for_project(project.id):
            if not row.is_public:
                continue
            channel = guild.get_channel(row.channel_id)
            if channel is None:
                continue
            want = overwrites.public_everyone_overwrite(row.public_can_post)
            current = channel.overwrites.get(guild.default_role)
            if everyone_ow_needed:
                await channel.edit(sync_permissions=True, reason=reason)
            if everyone_ow_needed or not _same_overwrite(current, want):
                await channel.set_permissions(guild.default_role, overwrite=want, reason=reason)
                report.fixed.append(f"restored public access on #{channel.name}")

        # 6. Owners
        if not roles[Tier.OWNER].members:
            creator = guild.get_member(project.creator_id)
            if creator is not None:
                await creator.add_roles(roles[Tier.OWNER], reason=reason)
                report.fixed.append("gave the owner role back to the creator")
            else:
                report.problems.append("the project has no owners; an admin should assign one")

    async def repair_guild(self, guild: Any) -> list[RepairReport]:
        reports = []
        for project in await self.repos.projects.list_for_guild(guild.id, REPAIRABLE):
            report = await self.repair(guild, project)
            if report.changed or report.problems:
                log.info("repaired %s: fixed=%s problems=%s",
                         project.name, report.fixed, report.problems)
            reports.append(report)
        return reports

    # ---- event hooks -------------------------------------------------------

    async def on_role_delete(self, guild: Any, role: Any) -> RepairReport | None:
        project = await self.repos.projects.get_by_role(role.id)
        if project is None or project.status not in REPAIRABLE:
            return None
        log.warning("project role %s of %s was deleted by hand", role.id, project.name)
        return await self.repair(guild, project)

    async def on_channel_delete(self, guild: Any, channel: Any) -> RepairReport | None:
        project = await self.repos.projects.get_by_category(channel.id)
        if project is not None:
            if project.status not in REPAIRABLE:
                return None
            log.warning("category of %s was deleted by hand", project.name)
            return await self.repair(guild, project)
        row = await self.repos.channels.get(channel.id)
        if row is not None:
            await self.repos.channels.remove(channel.id)
            owner = await self.repos.projects.get(row.project_id)
            if owner is not None and owner.status in REPAIRABLE:
                await self._audit(guild, owner, "channel.untrack", channel_id=channel.id)
        return None

    async def on_channel_placed(self, guild: Any, channel: Any) -> None:
        """A channel was created in, or moved into/out of, some category."""
        row = await self.repos.channels.get(channel.id)
        project = None
        if getattr(channel, "category_id", None):
            project = await self.repos.projects.get_by_category(channel.category_id)
        if project is not None and project.status not in REPAIRABLE:
            project = None
        if row is not None and (project is None or row.project_id != project.id):
            await self.repos.channels.remove(channel.id)
        if project is not None and (row is None or row.project_id != project.id):
            kind = kind_of(channel) or ChannelKind.TEXT
            await self.repos.channels.add(channel.id, project.id, kind, guild.me.id)

    async def cleanup_stale_pending(self, get_guild: Any, older_than_minutes: int = 10) -> int:
        """Drop reservations whose creation never finished (e.g. the bot crashed mid-saga)."""
        stale = await self.repos.projects.list_stale_pending(older_than_minutes)
        for project in stale:
            guild = get_guild(project.guild_id)
            if guild is not None:
                names = {overwrites.role_name(project.name, t) for t in Tier}
                for role in [r for r in guild.roles if r.name in names]:
                    if await self.repos.projects.get_by_role(role.id) is None:
                        await safe_delete(role, reason="Cleaning up a failed project creation")
            await self.repos.projects.delete(project.id)
            log.info("removed stale pending project %s", project.name)
        return len(stale)
