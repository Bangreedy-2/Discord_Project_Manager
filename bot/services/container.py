from dataclasses import dataclass

from bot.db.repos import Repos
from bot.services.channel_service import ChannelService
from bot.services.member_service import MemberService
from bot.services.project_service import ProjectService
from bot.services.reconcile import ReconcileService


@dataclass
class Services:
    projects: ProjectService
    channels: ChannelService
    members: MemberService
    reconcile: ReconcileService

    @classmethod
    def build(cls, repos: Repos) -> "Services":
        projects = ProjectService(repos)
        return cls(
            projects=projects,
            channels=ChannelService(repos, projects),
            members=MemberService(repos),
            reconcile=ReconcileService(repos),
        )
