from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.domain.models import Project
from bot.services import authz
from bot.services.project_service import remaining_project_slots
from bot.ui.autocomplete import all_projects, owned_projects
from bot.ui.confirm import confirm

if TYPE_CHECKING:
    from bot.main import Orchestrator


def _mentions(members: list[discord.Member]) -> str:
    return ", ".join(m.mention for m in members) if members else "—"


@app_commands.guild_only()
class ProjectsCog(commands.GroupCog, group_name="project", description="Manage projects"):
    def __init__(self, bot: "Orchestrator"):
        self.bot = bot
        super().__init__()

    @property
    def service(self):
        return self.bot.services.projects

    @app_commands.command(name="create", description="Create a new project")
    @app_commands.describe(name="Project name (max 80 characters)")
    @app_commands.checks.cooldown(1, 60, key=lambda i: (i.guild_id, i.user.id))
    async def create(self, interaction: discord.Interaction, name: str) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        project = await self.service.create(interaction.guild, interaction.user, name)
        await interaction.followup.send(
            f"Created **{project.name}**: <#{project.category_id}> is ready and you're its owner.",
            ephemeral=True,
        )

    @app_commands.command(name="delete", description="Delete a project and all its channels")
    @app_commands.autocomplete(project=owned_projects)
    async def delete(self, interaction: discord.Interaction, project: str) -> None:
        p = await self.service.resolve(interaction.guild_id, project)
        authz.require_creator_or_admin(p, interaction.user)
        ok = await confirm(
            interaction,
            f"Delete **{p.name}**? This removes its category, every channel in it and its roles. "
            "This cannot be undone.",
            confirm_label="Delete project",
        )
        if not ok:
            return
        await self.service.delete(interaction.guild, interaction.user, p)
        await interaction.edit_original_response(content=f"Deleted **{p.name}**.", view=None)

    @app_commands.command(name="info", description="Show a project's people and channels")
    @app_commands.autocomplete(project=all_projects)
    async def info(self, interaction: discord.Interaction, project: str) -> None:
        p = await self.service.resolve(interaction.guild_id, project)
        info = await self.service.info(interaction.guild, p)
        embed = discord.Embed(title=p.name, colour=discord.Colour.blurple())
        embed.add_field(name="Created by", value=f"<@{p.creator_id}>", inline=True)
        embed.add_field(name="Status", value=p.status.value, inline=True)
        embed.add_field(name="Owners", value=_mentions(info.owners), inline=False)
        embed.add_field(name="Members", value=_mentions(info.members), inline=False)
        embed.add_field(name="Viewers", value=_mentions(info.viewers), inline=False)
        lines = [
            f"{ch.mention if ch else f'`{row.channel_id}` (missing)'}"
            f"{' · public' if row.is_public else ''}"
            for row, ch in info.channels
        ]
        embed.add_field(name="Channels", value="\n".join(lines) or "—", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="list", description="List your projects and all active projects")
    async def list_(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        everything = await self.bot.repos.projects.list_for_guild(guild.id)
        settings = await self.bot.repos.settings.get(guild.id)
        created = await self.bot.repos.projects.count_for_creator(guild.id, interaction.user.id)

        def fmt(p: Project) -> str:
            tier = authz.tier_of(p, interaction.user)
            return f"**{p.name}**" + (f" · {tier.value}" if tier else "")

        mine = [p for p in everything if authz.tier_of(p, interaction.user)]
        embed = discord.Embed(title="Projects", colour=discord.Colour.blurple())
        embed.add_field(
            name="Yours", value="\n".join(fmt(p) for p in mine)[:1024] or "—", inline=False
        )
        embed.add_field(
            name=f"All active ({len(everything)})",
            value="\n".join(p.name for p in everything)[:1024] or "—",
            inline=False,
        )
        cap = "no limit (admin)" if authz.is_admin(interaction.user) else (
            f"{created}/{settings.max_projects_per_user}"
        )
        embed.set_footer(
            text=f"You've created {cap} · "
            f"server has room for {remaining_project_slots(guild)} more projects"
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: "Orchestrator") -> None:
    await bot.add_cog(ProjectsCog(bot))
