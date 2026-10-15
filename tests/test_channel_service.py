import pytest

from bot.domain.models import ChannelKind
from bot.errors import ChannelCapReached, InvalidTarget, NotInProject, NotOwner
from bot.services.channel_service import ChannelService
from bot.services.project_service import ProjectService
from tests.fake_discord import Guild
from tests.memory_repos import memory_repos


@pytest.fixture
async def env():
    repos = memory_repos()
    guild = Guild()
    projects = ProjectService(repos)
    svc = ChannelService(repos, projects)
    alice = guild.add_member(10)
    project = await projects.create(guild, alice, "Apollo")
    return repos, guild, svc, alice, project


async def test_owner_creates_channels_of_each_kind(env):
    repos, guild, svc, alice, p = env
    for kind in ChannelKind:
        ch = await svc.create(guild, alice, p, f"c-{kind.value}", kind)
        assert ch.category_id == p.category_id and ch.kind is kind
        assert (await repos.channels.get(ch.id)).kind is kind
    assert repos.audit.actions.count("channel.create") == 3


async def test_non_owner_cannot_create(env):
    _, guild, svc, _, p = env
    member = guild.add_member(11)
    member.roles.append(guild.get_role(p.member_role_id))
    with pytest.raises(NotOwner):
        await svc.create(guild, member, p, "nope", ChannelKind.TEXT)


async def test_channel_cap(env):
    repos, guild, svc, alice, p = env
    # The project starts with its 4 default channels.
    await repos.settings.update(guild.id, max_channels_per_proj=5)
    await svc.create(guild, alice, p, "fifth", ChannelKind.TEXT)
    with pytest.raises(ChannelCapReached):
        await svc.create(guild, alice, p, "third", ChannelKind.TEXT)


async def test_rename_topic_delete(env):
    repos, guild, svc, alice, p = env
    ch = await svc.create(guild, alice, p, "notes", ChannelKind.TEXT)
    await svc.rename(ch, alice, "docs")
    assert ch.name == "docs"
    await svc.topic(ch, alice, "Design docs")
    assert ch.topic == "Design docs"
    voice = await svc.create(guild, alice, p, "call", ChannelKind.VOICE)
    with pytest.raises(InvalidTarget):
        await svc.topic(voice, alice, "nope")
    await svc.delete(ch, alice)
    assert guild.get_channel(ch.id) is None
    assert await repos.channels.get(ch.id) is None


async def test_owner_of_other_project_cannot_touch_channel(env):
    repos, guild, svc, alice, p = env
    bob = guild.add_member(11)
    await svc.projects.create(guild, bob, "Hermes")
    general = guild.get_channel(p.category_id).channels[0]
    with pytest.raises(NotOwner):
        await svc.rename(general, bob, "hijacked")


async def test_channel_outside_any_project_rejected(env):
    _, guild, svc, alice, _ = env
    loose = await guild.create_text_channel("lobby")
    with pytest.raises(NotInProject):
        await svc.rename(loose, alice, "x")


async def test_visibility_public_then_private(env):
    repos, guild, svc, alice, p = env
    ch = guild.get_channel(p.category_id).channels[0]
    await svc.set_visibility(ch, alice, True)
    ow = ch.overwrites[guild.default_role]
    assert ow.view_channel is True and ow.send_messages is False
    assert ch.synced is False
    assert (await repos.channels.get(ch.id)).is_public

    await svc.set_visibility(ch, alice, False)
    assert ch.synced is True
    assert ch.overwrites[guild.default_role].view_channel is False
    assert not (await repos.channels.get(ch.id)).is_public


async def test_visibility_tracks_hand_made_channel(env):
    repos, guild, svc, alice, p = env
    category = guild.get_channel(p.category_id)
    hand_made = await category.create_text_channel("manual")
    await svc.set_visibility(hand_made, alice, True)
    assert (await repos.channels.get(hand_made.id)).is_public
