"""Phase 1 smoke test: reserve projects for one user until the cap is hit.

Usage: DATABASE_URL=... python -m scripts.check_cap
Creates rows in a throwaway guild id and deletes them afterwards.
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

from bot.db.pool import create_pool
from bot.db.projects_repo import ProjectsRepo
from bot.errors import CapReached

GUILD = 1  # not a real snowflake, so it can't collide with a real server
USER = 42


async def main() -> int:
    load_dotenv()
    pool = await create_pool(os.environ["DATABASE_URL"])
    repo = ProjectsRepo(pool)
    try:
        for i in range(3):
            pid = await repo.reserve(GUILD, USER, f"cap-check-{i}", bypass=False)
            print(f"reserved {pid}")
        try:
            await repo.reserve(GUILD, USER, "cap-check-3", bypass=False)
        except CapReached:
            print("4th reservation raised CapReached as expected")
            return 0
        print("ERROR: 4th reservation succeeded")
        return 1
    finally:
        await pool.execute("delete from projects where guild_id = $1", GUILD)
        await pool.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
