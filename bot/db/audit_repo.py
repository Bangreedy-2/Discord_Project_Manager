import asyncpg

from bot.domain.models import AuditEntry


class AuditRepo:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def write(self, entry: AuditEntry) -> None:
        await self.pool.execute(
            """insert into audit_log (guild_id, project_id, actor_id, action, target_id, details)
               values ($1, $2, $3, $4, $5, $6)""",
            entry.guild_id, entry.project_id, entry.actor_id, entry.action,
            entry.target_id, entry.details,
        )
