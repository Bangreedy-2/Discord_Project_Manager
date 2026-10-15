from typing import TYPE_CHECKING

import discord
from discord import app_commands

if TYPE_CHECKING:
    from bot.main import Orchestrator


async def owned_projects(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    """Project names the invoker owns (admins see all)."""
    bot: "Orchestrator" = interaction.client  # type: ignore[assignment]
    if interaction.guild is None or not isinstance(interaction.user, discord.Member):
        return []
    projects = await bot.services.projects.list_owned(interaction.guild, interaction.user)
    needle = current.lower()
    return [
        app_commands.Choice(name=p.name, value=p.name)
        for p in projects
        if needle in p.name.lower()
    ][:25]


async def all_projects(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    bot: "Orchestrator" = interaction.client  # type: ignore[assignment]
    if interaction.guild is None:
        return []
    projects = await bot.repos.projects.list_for_guild(interaction.guild.id)
    needle = current.lower()
    return [
        app_commands.Choice(name=p.name, value=p.name)
        for p in projects
        if needle in p.name.lower()
    ][:25]
