import pytest

from bot.domain.models import Tier
from bot.errors import NotCreator, NotInProject, NotOwner
from bot.services import authz
from tests.fakes import FakeChannel, FakeMember, FakeRole, make_project


@pytest.fixture
def project():
    return make_project()


def test_owner_passes(project):
    owner = FakeMember(20, roles=[FakeRole(101)])
    authz.require_owner(project, owner)
    assert authz.tier_of(project, owner) is Tier.OWNER


@pytest.mark.parametrize("role_id", [102, 103, 999])
def test_non_owner_rejected(project, role_id):
    with pytest.raises(NotOwner):
        authz.require_owner(project, FakeMember(21, roles=[FakeRole(role_id)]))


def test_admin_passes_without_roles(project):
    admin = FakeMember(22, admin=True)
    authz.require_owner(project, admin)
    authz.require_creator_or_admin(project, admin)
    assert authz.tier_of(project, admin) is None


def test_owner_of_other_project_rejected(project):
    other = make_project(owner_role_id=201, member_role_id=202, viewer_role_id=203)
    with pytest.raises(NotOwner):
        authz.require_owner(project, FakeMember(23, roles=[FakeRole(201)]))
    authz.require_owner(other, FakeMember(23, roles=[FakeRole(201)]))


def test_tier_of(project):
    assert authz.tier_of(project, FakeMember(1, roles=[FakeRole(102)])) is Tier.MEMBER
    assert authz.tier_of(project, FakeMember(1, roles=[FakeRole(103)])) is Tier.VIEWER


def test_creator_only(project):
    authz.require_creator_or_admin(project, FakeMember(project.creator_id))
    with pytest.raises(NotCreator):
        authz.require_creator_or_admin(project, FakeMember(99, roles=[FakeRole(101)]))


def test_channel_in_project(project):
    assert authz.channel_in_project(FakeChannel(1, category_id=100), project)
    assert not authz.channel_in_project(FakeChannel(1, category_id=555), project)
    assert not authz.channel_in_project(FakeChannel(1, category_id=None), project)
    with pytest.raises(NotInProject):
        authz.require_channel_in_project(FakeChannel(1, category_id=555), project)


def test_channel_in_project_without_category(project):
    p = make_project(category_id=None)
    assert not authz.channel_in_project(FakeChannel(1, category_id=None), p)
