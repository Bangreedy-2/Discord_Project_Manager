import pytest

from bot.domain.models import ChannelKind, ProjectStatus
from bot.errors import CapReached, DuplicateName, NotCreator, RoleSlotsExhausted
from bot.services.project_service import ProjectService
from tests.fake_discord import Boom, Guild, Role
from tests.memory_repos import memory_repos


@pytest.fixture
def env():
    repos = memory_repos()
    guild = Guild()
    return repos, guild, ProjectService(repos)


async def test_create_builds_everything(env):
    repos, guild, svc = env
    alice = guild.add_member(10)
    p = await svc.create(guild, alice, "  Apollo ")

    assert p.name == "Apollo" and p.status is ProjectStatus.ACTIVE
    names = sorted(r.name for r in guild.roles if not r.is_default())
    assert names == ["◆ Apollo · Member", "◆ Apollo · Owner", "◆ Apollo · Viewer"]
    category = guild.get_channel(p.category_id)
    assert category.name == "Apollo"
    assert category.overwrites[guild.default_role].view_channel is False
    channels = category.channels
    assert [(c.name, c.kind) for c in channels] == [
        ("general", ChannelKind.TEXT),
        ("resources", ChannelKind.TEXT),
        ("public-info", ChannelKind.TEXT),
        ("Meeting Room", ChannelKind.VOICE),
    ]
    for c in channels:
        row = await repos.channels.get(c.id)
        assert row is not None and row.is_public is (c.name == "public-info")
    public = channels[2]
    assert public.overwrites[guild.default_role].view_channel is True
    assert public.overwrites[guild.default_role].send_messages is False
    for c in (channels[0], channels[1], channels[3]):
        assert c.overwrites[guild.default_role].view_channel is False
    assert guild.get_role(p.owner_role_id) in alice.roles
    assert repos.audit.actions == ["project.create"]


@pytest.mark.parametrize("step", ["create_role", "create_category", "create_channel", "add_roles"])
async def test_failure_rolls_back_everything(env, step):
    repos, guild, svc = env
    alice = guild.add_member(10)
    guild.fail_on = {step}
    with pytest.raises(Boom):
        await svc.create(guild, alice, "Apollo")
    assert guild.roles == [guild.default_role]
    assert guild.channels == []
    assert repos.projects.rows == {}
    assert repos.channels.rows == {}
    assert alice.roles == []


async def test_cap_and_admin_bypass(env):
    repos, guild, svc = env
    alice = guild.add_member(10)
    for i in range(3):
        await svc.create(guild, alice, f"P{i}")
    with pytest.raises(CapReached):
        await svc.create(guild, alice, "P3")
    admin = guild.add_member(11, admin=True)
    for i in range(4):
        await svc.create(guild, admin, f"A{i}")


async def test_duplicate_name(env):
    _, guild, svc = env
    await svc.create(guild, guild.add_member(10), "Apollo")
    with pytest.raises(DuplicateName):
        await svc.create(guild, guild.add_member(11), "apollo")


async def test_refuses_when_role_slots_run_out(env):
    _, guild, svc = env
    guild.roles += [Role(guild, 5000 + i, "x") for i in range(248)]
    with pytest.raises(RoleSlotsExhausted):
        await svc.create(guild, guild.add_member(10), "Apollo")


async def test_delete_removes_everything(env):
    repos, guild, svc = env
    alice = guild.add_member(10)
    p = await svc.create(guild, alice, "Apollo")
    category = guild.get_channel(p.category_id)
    await category.create_voice_channel("voice")
    # a channel deleted by hand earlier must not break deletion
    await category.channels[0].delete()

    await svc.delete(guild, alice, p)
    assert guild.channels == []
    assert guild.roles == [guild.default_role]
    assert repos.projects.rows == {}
    assert "project.delete" in repos.audit.actions


async def test_only_creator_or_admin_can_delete(env):
    _, guild, svc = env
    alice = guild.add_member(10)
    p = await svc.create(guild, alice, "Apollo")
    co_owner = guild.add_member(11)
    co_owner.roles.append(guild.get_role(p.owner_role_id))
    with pytest.raises(NotCreator):
        await svc.delete(guild, co_owner, p)
    await svc.delete(guild, guild.add_member(12, admin=True), p)


async def test_list_owned(env):
    _, guild, svc = env
    alice, bob = guild.add_member(10), guild.add_member(11)
    a = await svc.create(guild, alice, "A")
    await svc.create(guild, bob, "B")
    assert [p.name for p in await svc.list_owned(guild, alice)] == ["A"]
    admin = guild.add_member(12, admin=True)
    assert [p.name for p in await svc.list_owned(guild, admin)] == ["A", "B"]
    info = await svc.info(guild, a)
    assert info.owners == [alice] and info.members == [] and len(info.channels) == 4
