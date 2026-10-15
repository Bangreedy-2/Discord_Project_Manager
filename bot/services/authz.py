"""Authorization rules. Works on anything shaped like discord.Member / channels."""

from typing import Any

from bot.domain.models import Project, Tier
from bot.errors import NotCreator, NotInProject, NotOwner


def is_admin(member: Any) -> bool:
    return bool(member.guild_permissions.administrator)


def _role_ids(member: Any) -> set[int]:
    return {r.id for r in member.roles}


def tier_of(project: Project, member: Any) -> Tier | None:
    roles = _role_ids(member)
    for tier in (Tier.OWNER, Tier.MEMBER, Tier.VIEWER):
        role_id = project.role_id(tier)
        if role_id and role_id in roles:
            return tier
    return None


def is_owner(project: Project, member: Any) -> bool:
    return bool(project.owner_role_id) and project.owner_role_id in _role_ids(member)


def can_manage(project: Project, member: Any) -> bool:
    return is_admin(member) or is_owner(project, member)


def require_owner(project: Project, member: Any) -> None:
    if not can_manage(project, member):
        raise NotOwner()


def require_creator_or_admin(project: Project, member: Any) -> None:
    if not (is_admin(member) or project.creator_id == member.id):
        raise NotCreator()


def channel_in_project(channel: Any, project: Project) -> bool:
    category_id = getattr(channel, "category_id", None)
    return project.category_id is not None and category_id == project.category_id


def require_channel_in_project(channel: Any, project: Project) -> None:
    if not channel_in_project(channel, project):
        raise NotInProject()
