import pytest

from bot.domain.models import ProjectStatus, Tier
from bot.services import authz
from bot.services.channel_service import ChannelService
from bot.services.member_service import MemberService
from bot.services.project_service import ProjectService
from bot.services.reconcile import ReconcileService
from tests.fake_discord import Guild
from tests.memory_repos import memory_repos


@pytest.fixture
async def env():
    repos = memory_repos()
    guild = Guild()
    projects = ProjectService(repos)
    alice = guild.add_member(10)
    project = await projects.create(guild, alice, "Apollo")
    return repos, guild, ReconcileService(repos), projects, alice, project


async def test_healthy_project_needs_no_changes(env):
    repos, guild, rec, _, _, p = env
    report = await rec.repair(guild, p)
    assert not report.changed and not report.problems
    assert "project.repair" not in repos.audit.actions


async def test_deleted_member_role_is_recreated(env):
    repos, guild, rec, _, alice, p = env
    old = guild.get_role(p.member_role_id)
    await old.delete()
    report = await rec.on_role_delete(guild, old)
    fresh = await repos.projects.get(p.id)
    assert fresh.member_role_id != old.id
    new_role = guild.get_role(fresh.member_role_id)
    assert new_role.name == "◆ Apollo · Member"
    category = guild.get_channel(p.category_id)
    assert category.overwrites[new_role].send_messages is True
    assert "recreated the member role" in report.fixed
    assert fresh.status is ProjectStatus.ACTIVE


async def test_deleted_owner_role_goes_back_to_creator(env):
    repos, guild, rec, _, alice, p = env
    old = guild.get_role(p.owner_role_id)
    await old.delete()
    await rec.on_role_delete(guild, old)
    fresh = await repos.projects.get(p.id)
    assert authz.is_owner(fresh, alice)


async def test_ownerless_project_is_flagged_broken(env):
    repos, guild, rec, _, alice, p = env
    guild.members.remove(alice)
    old = guild.get_role(p.owner_role_id)
    await old.delete()
    report = await rec.on_role_delete(guild, old)
    assert report.problems
    assert (await repos.projects.get(p.id)).status is ProjectStatus.BROKEN


async def test_deleted_category_is_recreated_and_channels_return(env):
    repos, guild, rec, _, _, p = env
    category = guild.get_channel(p.category_id)
    general = category.channels[0]
    await category.delete()
    general.category_id = None  # Discord leaves orphaned channels uncategorised
    await rec.on_channel_delete(guild, category)
    fresh = await repos.projects.get(p.id)
    assert fresh.category_id != category.id
    assert general.category_id == fresh.category_id


async def test_hand_deleted_channel_is_untracked(env):
    repos, guild, rec, _, _, p = env
    general = guild.get_channel(p.category_id).channels[0]
    await general.delete()
    await rec.on_channel_delete(guild, general)
    assert await repos.channels.get(general.id) is None


async def test_hand_created_channel_is_tracked_and_moving_out_untracks(env):
    repos, guild, rec, _, _, p = env
    category = guild.get_channel(p.category_id)
    manual = await category.create_text_channel("manual")
    await rec.on_channel_placed(guild, manual)
    assert (await repos.channels.get(manual.id)).project_id == p.id
    manual.category_id = None
    await rec.on_channel_placed(guild, manual)
    assert await repos.channels.get(manual.id) is None


async def test_public_overwrite_restored(env):
    repos, guild, rec, projects, alice, p = env
    channels = ChannelService(repos, projects)
    general = guild.get_channel(p.category_id).channels[0]
    await channels.set_visibility(general, alice, True)
    del general.overwrites[guild.default_role]  # an admin removed it by hand
    report = await rec.repair(guild, p)
    assert general.overwrites[guild.default_role].view_channel is True
    assert any("public" in f for f in report.fixed)


async def test_public_channel_gets_new_roles_after_role_recreation(env):
    repos, guild, rec, projects, alice, p = env
    channels = ChannelService(repos, projects)
    general = guild.get_channel(p.category_id).channels[0]
    await channels.set_visibility(general, alice, True)
    old = guild.get_role(p.viewer_role_id)
    await old.delete()
    await rec.on_role_delete(guild, old)
    fresh = await repos.projects.get(p.id)
    assert guild.get_role(fresh.viewer_role_id) in general.overwrites
    assert general.overwrites[guild.default_role].view_channel is True


async def test_deleting_project_is_ignored(env):
    repos, guild, rec, _, _, p = env
    await repos.projects.set_status(p.id, ProjectStatus.DELETING)
    old = guild.get_role(p.owner_role_id)
    await old.delete()
    assert await rec.on_role_delete(guild, old) is None


async def test_stale_pending_cleanup(env):
    repos, guild, rec, _, _, _ = env
    pid = await repos.projects.reserve(guild.id, 20, "Ghost", bypass=False)
    leftover = await guild.create_role(name="◆ Ghost · Owner", permissions=None,
                                       mentionable=False, hoist=False)
    assert await rec.cleanup_stale_pending(lambda gid: guild) == 1
    assert await repos.projects.get(pid) is None
    assert leftover not in guild.roles


async def test_member_service_unaffected(env):
    repos, guild, rec, _, alice, p = env
    bob = guild.add_member(11)
    await MemberService(repos).set_tier(guild, alice, p, bob, Tier.VIEWER)
    report = await rec.repair(guild, p)
    assert not report.changed
