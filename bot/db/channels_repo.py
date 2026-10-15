from uuid import UUID

import asyncpg

from bot.domain.models import ChannelKind, ProjectChannel

_COLUMNS = "channel_id, project_id, kind, is_public, public_can_post, created_by, created_at"


class ChannelsRepo:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def add(
        self, channel_id: int, project_id: UUID, kind: ChannelKind, created_by: int
    ) -> None:
        await self.pool.execute(
            """insert into project_channels (channel_id, project_id, kind, created_by)
               values ($1, $2, $3, $4) on conflict (channel_id) do nothing""",
            channel_id, project_id, kind.value, created_by,
        )

    async def remove(self, channel_id: int) -> None:
        await self.pool.execute("delete from project_channels where channel_id = $1", channel_id)

    async def get(self, channel_id: int) -> ProjectChannel | None:
        r = await self.pool.fetchrow(
            f"select {_COLUMNS} from project_channels where channel_id = $1", channel_id
        )
        return ProjectChannel.from_record(r) if r else None

    async def list_for_project(self, project_id: UUID) -> list[ProjectChannel]:
        rows = await self.pool.fetch(
            f"""select {_COLUMNS} from project_channels
                 where project_id = $1 order by created_at""",
            project_id,
        )
        return [ProjectChannel.from_record(r) for r in rows]

    async def count_for_project(self, project_id: UUID) -> int:
        return await self.pool.fetchval(
            "select count(*) from project_channels where project_id = $1", project_id
        )

    async def set_public(self, channel_id: int, is_public: bool) -> None:
        await self.pool.execute(
            "update project_channels set is_public = $2 where channel_id = $1",
            channel_id, is_public,
        )
