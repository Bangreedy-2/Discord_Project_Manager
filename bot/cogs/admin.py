from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.domain.models import AuditEntry
from bot.ui.autocomplete import owned_projects

if TYPE_CHECKING:
    from bot.main import Orchestrator


def _is_admin(interaction: discord.Interaction) -> bool:
    return isinstance(interaction.user, discord.Member) and (
        interaction.user.guild_permissions.administrator
    )


@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
class AdminCog(commands.GroupCog, group_name="orchestrator", description="Server admin tools"):
    def __init__(self, bot: "Orchestrator"):
        self.bot = bot
        super().__init__()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not _is_admin(interaction):
            raise app_commands.CheckFailure("admin only")
        return True

    @app_commands.command(name="settings", description="View or change the project limits")
    @app_commands.describe(
        max_projects="Projects each user may create (admins are exempt)",
        max_channels="Channels allowed per project",
    )
    async def settings(
        self,
        interaction: discord.Interaction,
        max_projects: app_commands.Range[int, 0, 50] | None = None,
        max_channels: app_commands.Range[int, 1, 50] | None = None,
    ) -> None:
        repo = self.bot.repos.settings
        if max_projects is None and max_channels is None:
            s = await repo.get(interaction.guild_id)
            verb = "Current"
        else:
            s = await repo.update(interaction.guild_id, max_projects, max_channels)
            verb = "Updated"
            await self.bot.repos.audit.write(AuditEntry(
                interaction.guild_id, interaction.user.id, "settings.update",
                details={"max_projects_per_user": s.max_projects_per_user,
                         "max_channels_per_proj": s.max_channels_per_proj},
            ))
        await interaction.response.send_message(
            f"{verb} settings: **{s.max_projects_per_user}** projects per user, "
            f"**{s.max_channels_per_proj}** channels per project.",
            ephemeral=True,
        )

    @app_commands.command(name="repair", description="Check a project (or all) and fix drift")
    @app_commands.autocomplete(project=owned_projects)
    async def repair(self, interaction: discord.Interaction, project: str | None = None) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        reconcile = self.bot.services.reconcile
        if project:
            p = await self.bot.services.projects.resolve(interaction.guild_id, project)
            reports = [await reconcile.repair(interaction.guild, p)]
        else:
            reports = await reconcile.repair_guild(interaction.guild)
        lines = []
        for r in reports:
            if r.problems:
                lines.append(f"**{r.project}**: needs attention: {'; '.join(r.problems)}")
            elif r.fixed:
                lines.append(f"**{r.project}**: fixed {'; '.join(r.fixed)}")
        summary = "\n".join(lines) or f"Checked {len(reports)} project(s); everything is in order."
        await interaction.followup.send(summary[:2000], ephemeral=True)


async def setup(bot: "Orchestrator") -> None:
    await bot.add_cog(AdminCog(bot))
