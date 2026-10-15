from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.domain.models import ChannelKind
from bot.ui.autocomplete import owned_projects
from bot.ui.confirm import confirm

if TYPE_CHECKING:
    from bot.main import Orchestrator

ProjectChannelArg = discord.TextChannel | discord.VoiceChannel | discord.ForumChannel


@app_commands.guild_only()
class ChannelsCog(commands.GroupCog, group_name="channel", description="Manage project channels"):
    def __init__(self, bot: "Orchestrator"):
        self.bot = bot
        super().__init__()

    @property
    def service(self):
        return self.bot.services.channels

    @app_commands.command(name="create", description="Create a channel in one of your projects")
    @app_commands.autocomplete(project=owned_projects)
    @app_commands.choices(type=[
        app_commands.Choice(name="text", value="text"),
        app_commands.Choice(name="voice", value="voice"),
        app_commands.Choice(name="forum", value="forum"),
    ])
    async def create(
        self,
        interaction: discord.Interaction,
        project: str,
        name: str,
        type: app_commands.Choice[str] | None = None,
    ) -> None:
        p = await self.bot.services.projects.resolve(interaction.guild_id, project)
        kind = ChannelKind(type.value) if type else ChannelKind.TEXT
        await interaction.response.defer(ephemeral=True)
        channel = await self.service.create(interaction.guild, interaction.user, p, name, kind)
        await interaction.followup.send(f"Created {channel.mention} in **{p.name}**.", ephemeral=True)

    @app_commands.command(name="rename", description="Rename a project channel")
    async def rename(
        self, interaction: discord.Interaction, channel: ProjectChannelArg, name: str
    ) -> None:
        await self.service.rename(channel, interaction.user, name)
        await interaction.response.send_message(f"Renamed to {channel.mention}.", ephemeral=True)

    @app_commands.command(name="topic", description="Set a project channel's topic")
    async def topic(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | discord.ForumChannel,
        text: str,
    ) -> None:
        await self.service.topic(channel, interaction.user, text)
        await interaction.response.send_message(
            f"Updated the topic of {channel.mention}.", ephemeral=True
        )

    @app_commands.command(name="delete", description="Delete a project channel")
    async def delete(self, interaction: discord.Interaction, channel: ProjectChannelArg) -> None:
        # Run the ownership checks before asking for confirmation.
        await self.service._project_for(channel, interaction.user)
        ok = await confirm(
            interaction, f"Delete {channel.mention}? Its messages will be lost.",
            confirm_label="Delete channel",
        )
        if not ok:
            return
        name = channel.name
        await self.service.delete(channel, interaction.user)
        await interaction.edit_original_response(content=f"Deleted **#{name}**.", view=None)

    @app_commands.command(
        name="visibility",
        description="Make a project channel public (read-only for everyone) or private",
    )
    async def visibility(
        self, interaction: discord.Interaction, channel: ProjectChannelArg, public: bool
    ) -> None:
        await self.service.set_visibility(channel, interaction.user, public)
        state = (
            "public: everyone can read it, only project members can post"
            if public else "private: only project members can see it"
        )
        await interaction.response.send_message(f"{channel.mention} is now {state}.", ephemeral=True)


async def setup(bot: "Orchestrator") -> None:
    await bot.add_cog(ChannelsCog(bot))
