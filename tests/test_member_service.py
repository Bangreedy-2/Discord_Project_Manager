import pytest

from bot.domain.models import Tier
from bot.errors import InvalidTarget, LastOwner, NotOwner
from bot.services import authz
from bot.services.member_service import MemberService
from bot.services.project_service import ProjectService
from tests.fake_discord import Guild, Role
from tests.memory_repos import memory_repos


@pytest.fixture
async def env():
    repos = memory_repos()
    guild = Guild()
    projects = ProjectService(repos)
    alice = guild.add_member(10)
    project = await projects.create(guild, alice, "Apollo")
    return repos, guild, MemberService(repos), projects, alice, project


async def test_set_and_change_tier_keeps_one_role(env):
    repos, guild, svc, _, alice, p = env
    unrelated = Role(guild, 9999, "Unrelated")
    guild.roles.append(unrelated)
    bob = guild.add_member(11, roles=[unrelated])

    assert await svc.set_tier(guild, alice, p, bob, Tier.VIEWER) is None
    assert authz.tier_of(p, bob) is Tier.VIEWER
    assert await svc.set_tier(guild, alice, p, bob, Tier.MEMBER) is Tier.VIEWER
    held = [r.id for r in bob.roles if r.id in p.role_ids]
    assert held == [p.member_role_id]
    assert unrelated in bob.roles
    assert repos.audit.actions.count("member.set") == 2


async def test_cannot_demote_last_owner(env):
    _, guild, svc, _, alice, p = env
    with pytest.raises(LastOwner):
        await svc.set_tier(guild, alice, p, alice, Tier.MEMBER)
    with pytest.raises(LastOwner):
        await svc.remove(guild, alice, p, alice)


async def test_can_step_down_when_another_owner_exists(env):
    _, guild, svc, _, alice, p = env
    bob = guild.add_member(11)
    await svc.set_tier(guild, alice, p, bob, Tier.OWNER)
    await svc.set_tier(guild, alice, p, alice, Tier.VIEWER)
    assert authz.tier_of(p, alice) is Tier.VIEWER
    with pytest.raises(NotOwner):
        await svc.set_tier(guild, alice, p, bob, Tier.MEMBER)


async def test_owner_of_a_cannot_touch_b(env):
    _, guild, svc, projects, alice, p = env
    bob = guild.add_member(11)
    b = await projects.create(guild, bob, "Hermes")
    carol = guild.add_member(12)
    with pytest.raises(NotOwner):
        await svc.set_tier(guild, alice, b, carol, Tier.MEMBER)
    with pytest.raises(NotOwner):
        await svc.remove(guild, alice, b, bob)


async def test_non_owner_tiers_have_no_management(env):
    _, guild, svc, _, alice, p = env
    viewer = guild.add_member(11)
    await svc.set_tier(guild, alice, p, viewer, Tier.VIEWER)
    with pytest.raises(NotOwner):
        await svc.set_tier(guild, viewer, p, guild.add_member(12), Tier.MEMBER)


async def test_bots_rejected(env):
    _, guild, svc, _, alice, p = env
    with pytest.raises(InvalidTarget):
        await svc.set_tier(guild, alice, p, guild.add_member(50, bot=True), Tier.MEMBER)


async def test_remove(env):
    repos, guild, svc, _, alice, p = env
    bob = guild.add_member(11)
    await svc.set_tier(guild, alice, p, bob, Tier.MEMBER)
    await svc.remove(guild, alice, p, bob)
    assert authz.tier_of(p, bob) is None
    with pytest.raises(InvalidTarget):
        await svc.remove(guild, alice, p, bob)


async def test_admin_can_manage_without_role(env):
    _, guild, svc, _, _, p = env
    admin = guild.add_member(99, admin=True)
    bob = guild.add_member(11)
    await svc.set_tier(guild, admin, p, bob, Tier.OWNER)
    assert authz.is_owner(p, bob)
