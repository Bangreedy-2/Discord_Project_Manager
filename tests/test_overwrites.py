import pytest

from bot.domain.models import Tier
from bot.domain.overwrites import (
    category_overwrites,
    public_everyone_overwrite,
    role_name,
    validate_project_name,
)
from bot.errors import InvalidName
from tests.fakes import FakeGuild, FakeRole


@pytest.fixture
def setup():
    guild = FakeGuild()
    owner, member, viewer = FakeRole(11), FakeRole(12), FakeRole(13)
    return guild, owner, member, viewer, category_overwrites(guild, owner, member, viewer)


def test_everyone_cannot_see_category(setup):
    guild, *_, ow = setup
    everyone = ow[guild.default_role]
    assert everyone.view_channel is False
    assert everyone.connect is False


def test_owner_can_moderate(setup):
    _, owner, _, _, ow = setup
    assert ow[owner].view_channel and ow[owner].send_messages and ow[owner].manage_messages
    assert ow[owner].speak


def test_member_can_talk_but_not_moderate(setup):
    _, _, member, _, ow = setup
    assert ow[member].send_messages and ow[member].speak
    assert ow[member].manage_messages is None


def test_viewer_is_read_only(setup):
    _, _, _, viewer, ow = setup
    v = ow[viewer]
    assert v.view_channel and v.read_message_history and v.connect
    assert v.send_messages is False
    assert v.add_reactions is False
    assert v.create_public_threads is False
    assert v.send_messages_in_threads is False
    assert v.speak is False


def test_bot_keeps_management_rights(setup):
    guild, *_, ow = setup
    b = ow[guild.me]
    assert b.view_channel and b.manage_channels
    # Allowing manage_roles in an overwrite requires Administrator, so Discord rejects it.
    assert b.manage_roles is None


def test_no_project_role_gets_management_permissions(setup):
    _, owner, member, viewer, ow = setup
    for role in (owner, member, viewer):
        assert ow[role].manage_channels is None
        assert ow[role].manage_roles is None


def test_public_overwrite_read_only_by_default():
    o = public_everyone_overwrite()
    assert o.view_channel and o.read_message_history and o.connect
    assert o.send_messages is False and o.add_reactions is False and o.speak is False
    assert o.create_public_threads is False


def test_public_overwrite_can_post():
    o = public_everyone_overwrite(can_post=True)
    assert o.send_messages and o.add_reactions and o.speak
    assert o.create_public_threads is False


def test_role_name():
    assert role_name("Apollo", Tier.OWNER) == "◆ Apollo · Owner"


@pytest.mark.parametrize("raw,clean", [("  Apollo  ", "Apollo"), ("Big   Project", "Big Project")])
def test_validate_name_cleans(raw, clean):
    assert validate_project_name(raw) == clean


@pytest.mark.parametrize("bad", ["", "   ", "x" * 81, "a@b", "#chan", "◆ hi"])
def test_validate_name_rejects(bad):
    with pytest.raises(InvalidName):
        validate_project_name(bad)
