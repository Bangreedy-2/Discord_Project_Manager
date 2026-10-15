"""Project membership: one tier per user, never zero owners."""

from typing import Any

from bot.db.repos import Repos
from bot.domain.models import AuditEntry, Project, Tier
from bot.errors import InvalidTarget, LastOwner, ProjectBroken
from bot.services import authz


class MemberService:
    def __init__(self, repos: Repos):
        self.repos = repos

    def _roles(self, guild: Any, project: Project) -> dict[Tier, Any]:
        roles = {t: guild.get_role(project.role_id(t)) for t in Tier}
        if any(r is None for r in roles.values()):
            raise ProjectBroken()
        return roles

    def _guard_last_owner(self, project: Project, owner_role: Any, target: Any) -> None:
        if authz.is_owner(project, target):
            others = [m for m in owner_role.members if m.id != target.id]
            if not others:
                raise LastOwner()

    async def set_tier(
        self, guild: Any, actor: Any, project: Project, target: Any, tier: Tier
    ) -> Tier | None:
        """Give target exactly one project role. Returns their previous tier."""
        authz.require_owner(project, actor)
        if target.bot:
            raise InvalidTarget("Bots can't be added to projects.")
        roles = self._roles(guild, project)
        previous = authz.tier_of(project, target)
        if previous is tier:
            return previous
        if tier is not Tier.OWNER:
            self._guard_last_owner(project, roles[Tier.OWNER], target)

        project_role_ids = set(project.role_ids)
        new_roles = [r for r in target.roles if r.id not in project_role_ids and not r.is_default()]
        new_roles.append(roles[tier])
        # One edit call so the user is never left with zero or two project roles.
        await target.edit(roles=new_roles, reason=f"{actor} set {tier.value} in {project.name}")
        await self.repos.audit.write(
            AuditEntry(
                guild.id, actor.id, "member.set", project.id, target.id,
                {"tier": tier.value, "previous": previous.value if previous else None},
            )
        )
        return previous

    async def remove(self, guild: Any, actor: Any, project: Project, target: Any) -> Tier | None:
        authz.require_owner(project, actor)
        roles = self._roles(guild, project)
        previous = authz.tier_of(project, target)
        if previous is None:
            raise InvalidTarget(f"{target.display_name} isn't part of **{project.name}**.")
        self._guard_last_owner(project, roles[Tier.OWNER], target)
        held = [r for r in target.roles if r.id in set(project.role_ids)]
        await target.remove_roles(*held, reason=f"{actor} removed them from {project.name}")
        await self.repos.audit.write(
            AuditEntry(guild.id, actor.id, "member.remove", project.id, target.id,
                       {"previous": previous.value})
        )
        return previous
