import asyncpg

from bot.domain.models import GuildSettings


class SettingsRepo:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def get(self, guild_id: int) -> GuildSettings:
        r = await self.pool.fetchrow(
            """select guild_id, max_projects_per_user, max_channels_per_proj
                 from guild_settings where guild_id = $1""",
            guild_id,
        )
        if r is None:
            return GuildSettings(guild_id=guild_id)
        return GuildSettings(
            guild_id=r["guild_id"],
            max_projects_per_user=r["max_projects_per_user"],
            max_channels_per_proj=r["max_channels_per_proj"],
        )

    async def update(
        self,
        guild_id: int,
        max_projects_per_user: int | None = None,
        max_channels_per_proj: int | None = None,
    ) -> GuildSettings:
        r = await self.pool.fetchrow(
            """insert into guild_settings (guild_id, max_projects_per_user, max_channels_per_proj)
               values ($1, coalesce($2, 3), coalesce($3, 15))
               on conflict (guild_id) do update set
                 max_projects_per_user = coalesce($2, guild_settings.max_projects_per_user),
                 max_channels_per_proj = coalesce($3, guild_settings.max_channels_per_proj)
               returning guild_id, max_projects_per_user, max_channels_per_proj""",
            guild_id, max_projects_per_user, max_channels_per_proj,
        )
        return GuildSettings(
            guild_id=r["guild_id"],
            max_projects_per_user=r["max_projects_per_user"],
            max_channels_per_proj=r["max_channels_per_proj"],
        )
