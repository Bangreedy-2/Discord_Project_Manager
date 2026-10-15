"""Database tests. Run against a scratch Postgres with the migrations applied:

    TEST_DATABASE_URL=postgresql://postgres@localhost:5432/postgres pytest tests/test_db.py
"""

import asyncio
import os

import pytest

from bot.db.repos import Repos
from bot.domain.models import ChannelKind, ProjectStatus
from bot.errors import CapReached, DuplicateName

DSN = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="TEST_DATABASE_URL not set")

GUILD = 7


@pytest.fixture
async def repos():
    from bot.db.pool import create_pool

    pool = await create_pool(DSN)
    await pool.execute("delete from projects where guild_id = $1", GUILD)
    await pool.execute("delete from guild_settings where guild_id = $1", GUILD)
    yield Repos.from_pool(pool)
    await pool.execute("delete from projects where guild_id = $1", GUILD)
    await pool.execute("delete from guild_settings where guild_id = $1", GUILD)
    await pool.execute("delete from audit_log where guild_id = $1", GUILD)
    await pool.close()


async def test_cap_blocks_fourth_project(repos):
    for i in range(3):
        await repos.projects.reserve(GUILD, 1, f"p{i}", bypass=False)
    with pytest.raises(CapReached):
        await repos.projects.reserve(GUILD, 1, "p3", bypass=False)


async def test_admin_bypasses_cap(repos):
    for i in range(4):
        await repos.projects.reserve(GUILD, 1, f"p{i}", bypass=True)
    assert await repos.projects.count_for_creator(GUILD, 1) == 4


async def test_concurrent_reserves_respect_cap(repos):
    results = await asyncio.gather(
        *(repos.projects.reserve(GUILD, 2, f"c{i}", bypass=False) for i in range(6)),
        return_exceptions=True,
    )
    assert sum(not isinstance(r, Exception) for r in results) == 3
    assert all(isinstance(r, CapReached) for r in results if isinstance(r, Exception))


async def test_cap_comes_from_guild_settings(repos):
    await repos.settings.update(GUILD, max_projects_per_user=1)
    await repos.projects.reserve(GUILD, 3, "only", bypass=False)
    with pytest.raises(CapReached):
        await repos.projects.reserve(GUILD, 3, "second", bypass=False)


async def test_duplicate_name_case_insensitive(repos):
    await repos.projects.reserve(GUILD, 1, "Apollo", bypass=False)
    with pytest.raises(DuplicateName):
        await repos.projects.reserve(GUILD, 2, "apollo", bypass=False)


async def test_deleting_frees_name(repos):
    pid = await repos.projects.reserve(GUILD, 1, "Apollo", bypass=False)
    await repos.projects.set_status(pid, ProjectStatus.DELETING)
    await repos.projects.reserve(GUILD, 2, "Apollo", bypass=False)


async def test_activate_and_lookups(repos):
    pid = await repos.projects.reserve(GUILD, 1, "Hermes", bypass=False)
    await repos.projects.activate(pid, 100, 101, 102, 103)
    p = await repos.projects.get(pid)
    assert p.status is ProjectStatus.ACTIVE
    assert (await repos.projects.get_by_category(100)).id == pid
    assert (await repos.projects.get_by_role(102)).id == pid
    assert [x.id for x in await repos.projects.list_for_owner(GUILD, [101, 999])] == [pid]
    assert await repos.projects.list_for_owner(GUILD, [102]) == []


async def test_channels_cascade_on_project_delete(repos):
    pid = await repos.projects.reserve(GUILD, 1, "Zeus", bypass=False)
    await repos.channels.add(500, pid, ChannelKind.TEXT, 1)
    await repos.channels.set_public(500, True)
    assert (await repos.channels.get(500)).is_public
    await repos.projects.delete(pid)
    assert await repos.channels.get(500) is None
