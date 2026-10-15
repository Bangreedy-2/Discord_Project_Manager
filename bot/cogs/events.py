import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands, tasks

from bot.services.reconcile import ReconcileService

if TYPE_CHECKING:
    from bot.main import Orchestrator

log = logging.getLogger(__name__)


class EventsCog(commands.Cog):
    """Keeps projects consistent when someone edits Discord by hand."""

    def __init__(self, bot: "Orchestrator"):
        self.bot = bot
        self._reconciled_on_startup = False

    @property
    def reconcile(self) -> ReconcileService:
        return self.bot.services.reconcile

    async def cog_load(self) -> None:
        self.cleanup_pending.start()

    async def cog_unload(self) -> None:
        self.cleanup_pending.cancel()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if self._reconciled_on_startup:
            return
        self._reconciled_on_startup = True
        for guild in self.bot.guilds:
            try:
                await self.reconcile.repair_guild(guild)
            except Exception:
                log.exception("startup reconciliation failed for guild %s", guild.id)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        await self.reconcile.on_role_delete(role.guild, role)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        await self.reconcile.on_channel_delete(channel.guild, channel)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        if isinstance(channel, discord.CategoryChannel):
            return
        await self.reconcile.on_channel_placed(channel.guild, channel)

    @commands.Cog.listener()
    async def on_guild_channel_update(
        self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel
    ) -> None:
        if isinstance(after, discord.CategoryChannel) or before.category_id == after.category_id:
            return
        await self.reconcile.on_channel_placed(after.guild, after)

    @tasks.loop(minutes=10)
    async def cleanup_pending(self) -> None:
        try:
            await self.reconcile.cleanup_stale_pending(self.bot.get_guild)
        except Exception:
            log.exception("stale pending cleanup failed")

    @cleanup_pending.before_loop
    async def _before_cleanup(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: "Orchestrator") -> None:
    await bot.add_cog(EventsCog(bot))
