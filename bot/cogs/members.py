from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.domain.models import Tier
from bot.ui.autocomplete import owned_projects

if TYPE_CHECKING:
    from bot.main import Orchestrator


@app_commands.guild_only()
class MembersCog(commands.GroupCog, group_name="member", description="Manage project members"):
    def __init__(self, bot: "Orchestrator"):
        self.bot = bot
        super().__init__()

    @property
    def service(self):
        return self.bot.services.members

    @app_commands.command(name="set", description="Add someone to a project or change their role")
    @app_commands.autocomplete(project=owned_projects)
    @app_commands.choices(role=[
        app_commands.Choice(name="owner", value="owner"),
        app_commands.Choice(name="member", value="member"),
        app_commands.Choice(name="viewer", value="viewer"),
    ])
    async def set_(
        self,
        interaction: discord.Interaction,
        project: str,
        user: discord.Member,
        role: app_commands.Choice[str],
    ) -> None:
        p = await self.bot.services.projects.resolve(interaction.guild_id, project)
        tier = Tier(role.value)
        previous = await self.service.set_tier(interaction.guild, interaction.user, p, user, tier)
        if previous is tier:
            msg = f"{user.mention} is already a {tier.value} of **{p.name}**."
        elif previous is None:
            msg = f"Added {user.mention} to **{p.name}** as {tier.value}."
        else:
            msg = f"{user.mention} is now a {tier.value} of **{p.name}** (was {previous.value})."
        await interaction.response.send_message(
            msg, ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
        )

    @app_commands.command(name="remove", description="Remove someone from a project")
    @app_commands.autocomplete(project=owned_projects)
    async def remove(
        self, interaction: discord.Interaction, project: str, user: discord.Member
    ) -> None:
        p = await self.bot.services.projects.resolve(interaction.guild_id, project)
        await self.service.remove(interaction.guild, interaction.user, p, user)
        await interaction.response.send_message(
            f"Removed {user.mention} from **{p.name}**.",
            ephemeral=True, allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot: "Orchestrator") -> None:
    await bot.add_cog(MembersCog(bot))
