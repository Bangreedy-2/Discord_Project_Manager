import logging

import asyncpg
import discord
from discord import app_commands
from discord.ext import commands

from bot.config import Settings, load_settings
from bot.db.pool import create_pool
from bot.db.repos import Repos
from bot.errors import OrchestratorError
from bot.services.container import Services

log = logging.getLogger("orchestrator")

EXTENSIONS = (
    "bot.cogs.projects",
)


class Orchestrator(commands.Bot):
    pool: asyncpg.Pool
    repos: Repos
    services: Services

    def __init__(self, settings: Settings):
        intents = discord.Intents.default()
        # Needed to list role holders in /project info and to repair state on startup.
        intents.members = True
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.settings = settings
        self.tree.on_error = self.on_app_command_error

    async def setup_hook(self) -> None:
        self.pool = await create_pool(self.settings.database_url)
        self.repos = Repos.from_pool(self.pool)
        self.services = Services.build(self.repos)
        log.info("database pool ready")
        for ext in EXTENSIONS:
            await self.load_extension(ext)
        await self._sync_commands()

    async def close(self) -> None:
        await super().close()
        if getattr(self, "pool", None) is not None:
            await self.pool.close()

    async def _sync_commands(self) -> None:
        if self.settings.dev_guild_id:
            guild = discord.Object(id=self.settings.dev_guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info("synced %d commands to dev guild %s", len(synced), guild.id)
        else:
            synced = await self.tree.sync()
            log.info("synced %d global commands", len(synced))

    async def on_ready(self) -> None:
        log.info("logged in as %s (%s)", self.user, self.user.id if self.user else "?")

    async def on_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        original = getattr(error, "original", error)
        if isinstance(original, OrchestratorError):
            message = original.message
        elif isinstance(error, app_commands.CommandOnCooldown):
            message = f"Slow down! Try again in {error.retry_after:.0f} s."
        elif isinstance(error, app_commands.NoPrivateMessage):
            message = "This command only works inside a server."
        elif isinstance(error, app_commands.CheckFailure):
            message = "You can't use this command."
        elif isinstance(original, discord.Forbidden):
            message = (
                "I'm missing a Discord permission for that. Make sure my role has Manage Roles "
                "and Manage Channels and sits above the project roles."
            )
        else:
            log.exception(
                "unhandled error in /%s",
                interaction.command.qualified_name if interaction.command else "?",
                exc_info=original,
            )
            message = "Something went wrong. The error has been logged."
        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except discord.HTTPException:
            log.warning("could not deliver error message to %s", interaction.user)


def build_bot(settings: Settings) -> Orchestrator:
    bot = Orchestrator(settings)

    @bot.tree.command(name="ping", description="Check that the bot is alive")
    async def ping(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            f"Pong! {round(bot.latency * 1000)} ms", ephemeral=True
        )

    return bot


def main() -> None:
    settings = load_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    bot = build_bot(settings)
    bot.run(settings.discord_token, log_handler=None)


if __name__ == "__main__":
    main()
