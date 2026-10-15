from uuid import UUID

import asyncpg

from bot.domain.models import Project, ProjectStatus
from bot.errors import CapReached, DuplicateName

_COLUMNS = """id, guild_id, name, creator_id, status, category_id,
              owner_role_id, member_role_id, viewer_role_id, created_at"""


class ProjectsRepo:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def reserve(self, guild_id: int, creator_id: int, name: str, bypass: bool) -> UUID:
        try:
            return await self.pool.fetchval(
                "select reserve_project($1, $2, $3, $4)", guild_id, creator_id, name, bypass
            )
        except asyncpg.RaiseError as e:
            if "project_cap_reached" in str(e):
                raise CapReached() from e
            raise
        except asyncpg.UniqueViolationError as e:
            raise DuplicateName(name) from e

    async def activate(
        self,
        project_id: UUID,
        category_id: int,
        owner_role_id: int,
        member_role_id: int,
        viewer_role_id: int,
    ) -> None:
        await self.pool.execute(
            """update projects
                  set category_id = $2, owner_role_id = $3, member_role_id = $4,
                      viewer_role_id = $5, status = 'active'
                where id = $1""",
            project_id, category_id, owner_role_id, member_role_id, viewer_role_id,
        )

    async def set_status(self, project_id: UUID, status: ProjectStatus) -> None:
        await self.pool.execute(
            "update projects set status = $2 where id = $1", project_id, status.value
        )

    async def update_ids(self, project_id: UUID, **ids: int | None) -> None:
        allowed = {"category_id", "owner_role_id", "member_role_id", "viewer_role_id"}
        if not ids or not set(ids) <= allowed:
            raise ValueError(f"invalid columns: {set(ids) - allowed}")
        sets = ", ".join(f"{col} = ${i}" for i, col in enumerate(ids, start=2))
        await self.pool.execute(
            f"update projects set {sets} where id = $1", project_id, *ids.values()
        )

    async def delete(self, project_id: UUID) -> None:
        await self.pool.execute("delete from projects where id = $1", project_id)

    async def get(self, project_id: UUID) -> Project | None:
        r = await self.pool.fetchrow(f"select {_COLUMNS} from projects where id = $1", project_id)
        return Project.from_record(r) if r else None

    async def get_by_name(self, guild_id: int, name: str) -> Project | None:
        r = await self.pool.fetchrow(
            f"""select {_COLUMNS} from projects
                 where guild_id = $1 and lower(name) = lower($2) and status <> 'deleting'""",
            guild_id, name,
        )
        return Project.from_record(r) if r else None

    async def get_by_category(self, category_id: int) -> Project | None:
        r = await self.pool.fetchrow(
            f"select {_COLUMNS} from projects where category_id = $1", category_id
        )
        return Project.from_record(r) if r else None

    async def get_by_role(self, role_id: int) -> Project | None:
        r = await self.pool.fetchrow(
            f"""select {_COLUMNS} from projects
                 where $1 in (owner_role_id, member_role_id, viewer_role_id)""",
            role_id,
        )
        return Project.from_record(r) if r else None

    async def list_for_guild(
        self, guild_id: int, statuses: tuple[ProjectStatus, ...] = (ProjectStatus.ACTIVE,)
    ) -> list[Project]:
        rows = await self.pool.fetch(
            f"""select {_COLUMNS} from projects
                 where guild_id = $1 and status = any($2::text[])
                 order by lower(name)""",
            guild_id, [s.value for s in statuses],
        )
        return [Project.from_record(r) for r in rows]

    async def list_for_owner(self, guild_id: int, owner_role_ids: list[int]) -> list[Project]:
        """Projects whose owner role is among the given role ids (the invoker's roles)."""
        rows = await self.pool.fetch(
            f"""select {_COLUMNS} from projects
                 where guild_id = $1 and status in ('active','broken')
                   and owner_role_id = any($2::bigint[])
                 order by lower(name)""",
            guild_id, owner_role_ids,
        )
        return [Project.from_record(r) for r in rows]

    async def count_for_creator(self, guild_id: int, creator_id: int) -> int:
        return await self.pool.fetchval(
            """select count(*) from projects
                where guild_id = $1 and creator_id = $2
                  and status in ('pending','active','broken')""",
            guild_id, creator_id,
        )

    async def list_stale_pending(self, older_than_minutes: int = 10) -> list[Project]:
        rows = await self.pool.fetch(
            f"""select {_COLUMNS} from projects
                 where status = 'pending'
                   and created_at < now() - make_interval(mins => $1)""",
            older_than_minutes,
        )
        return [Project.from_record(r) for r in rows]
