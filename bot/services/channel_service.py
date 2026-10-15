"""Channel management inside a project's category."""

from typing import Any

import discord

from bot.db.repos import Repos
from bot.domain.models import AuditEntry, ChannelKind, Project
from bot.domain.overwrites import public_everyone_overwrite
from bot.errors import ChannelCapReached, InvalidTarget, NotInProject, ProjectBroken
from bot.services import authz
from bot.services.discord_utils import safe_delete
from bot.services.project_service import ProjectService

MAX_CHANNEL_NAME = 100
MAX_TOPIC = 1024


def kind_of(channel: Any) -> ChannelKind | None:
    if isinstance(channel, discord.VoiceChannel):
        return ChannelKind.VOICE
    if isinstance(channel, discord.ForumChannel):
        return ChannelKind.FORUM
    if isinstance(channel, discord.TextChannel):
        return ChannelKind.TEXT
    return getattr(channel, "kind", None)


class ChannelService:
    def __init__(self, repos: Repos, projects: ProjectService):
        self.repos = repos
        self.projects = projects

    async def _project_for(self, channel: Any, actor: Any) -> Project:
        project = await self.projects.resolve_by_category(getattr(channel, "category_id", None))
        if project is None:
            raise NotInProject()
        authz.require_owner(project, actor)
        authz.require_channel_in_project(channel, project)
        return project

    async def _audit(self, guild: Any, actor: Any, action: str, project: Project,
                     channel_id: int, **details: Any) -> None:
        await self.repos.audit.write(
            AuditEntry(guild.id, actor.id, action, project.id, channel_id, details)
        )

    async def create(
        self, guild: Any, actor: Any, project: Project, name: str, kind: ChannelKind
    ) -> Any:
        authz.require_owner(project, actor)
        name = name.strip()
        if not name or len(name) > MAX_CHANNEL_NAME:
            raise InvalidTarget(f"Channel names must be 1-{MAX_CHANNEL_NAME} characters.")
        settings = await self.repos.settings.get(guild.id)
        if await self.repos.channels.count_for_project(project.id) >= settings.max_channels_per_proj:
            raise ChannelCapReached(settings.max_channels_per_proj)
        category = guild.get_channel(project.category_id) if project.category_id else None
        if category is None:
            raise ProjectBroken()

        reason = f"{actor} in project {project.name}"
        if kind is ChannelKind.VOICE:
            channel = await category.create_voice_channel(name, reason=reason)
        elif kind is ChannelKind.FORUM:
            channel = await category.create_forum(name, reason=reason)
        else:
            channel = await category.create_text_channel(name, reason=reason)
        try:
            await self.repos.channels.add(channel.id, project.id, kind, actor.id)
        except BaseException:
            await safe_delete(channel, reason="Rolling back channel creation")
            raise
        await self._audit(guild, actor, "channel.create", project, channel.id,
                          name=channel.name, kind=kind.value)
        return channel

    async def rename(self, channel: Any, actor: Any, name: str) -> None:
        project = await self._project_for(channel, actor)
        name = name.strip()
        if not name or len(name) > MAX_CHANNEL_NAME:
            raise InvalidTarget(f"Channel names must be 1-{MAX_CHANNEL_NAME} characters.")
        old = channel.name
        await channel.edit(name=name, reason=f"{actor} in project {project.name}")
        await self._audit(channel.guild, actor, "channel.rename", project, channel.id,
                          old=old, new=name)

    async def topic(self, channel: Any, actor: Any, text: str) -> None:
        project = await self._project_for(channel, actor)
        if kind_of(channel) not in (ChannelKind.TEXT, ChannelKind.FORUM):
            raise InvalidTarget("Only text and forum channels have a topic.")
        if len(text) > MAX_TOPIC:
            raise InvalidTarget(f"Topics can be at most {MAX_TOPIC} characters.")
        await channel.edit(topic=text, reason=f"{actor} in project {project.name}")
        await self._audit(channel.guild, actor, "channel.topic", project, channel.id)

    async def delete(self, channel: Any, actor: Any) -> None:
        project = await self._project_for(channel, actor)
        await safe_delete(channel, reason=f"{actor} in project {project.name}")
        await self.repos.channels.remove(channel.id)
        await self._audit(channel.guild, actor, "channel.delete", project, channel.id,
                          name=channel.name)

    async def set_visibility(self, channel: Any, actor: Any, public: bool) -> None:
        project = await self._project_for(channel, actor)
        guild = channel.guild
        row = await self.repos.channels.get(channel.id)
        if row is None:
            kind = kind_of(channel) or ChannelKind.TEXT
            await self.repos.channels.add(channel.id, project.id, kind, actor.id)
            row = await self.repos.channels.get(channel.id)
        reason = f"{actor} made channel {'public' if public else 'private'}"
        if public:
            # Editing an overwrite unsyncs the channel from its category automatically.
            await channel.set_permissions(
                guild.default_role,
                overwrite=public_everyone_overwrite(row.public_can_post),
                reason=reason,
            )
        else:
            await channel.edit(sync_permissions=True, reason=reason)
        await self.repos.channels.set_public(channel.id, public)
        await self._audit(guild, actor, "channel.visibility", project, channel.id, public=public)
