import logging

import asyncpg
import discord
from discord.ext import commands

from bot.config import Settings, load_settings
from bot.db.pool import create_pool
from bot.db.repos import Repos

log = logging.getLogger("orchestrator")


class Orchestrator(commands.Bot):
    def __init__(self, settings: Settings):
        intents = discord.Intents.default()
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.settings = settings
        self.pool: asyncpg.Pool | None = None
        self.repos: Repos | None = None

    async def setup_hook(self) -> None:
        self.pool = await create_pool(self.settings.database_url)
        self.repos = Repos.from_pool(self.pool)
        log.info("database pool ready")
        await self._sync_commands()

    async def close(self) -> None:
        await super().close()
        if self.pool is not None:
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
