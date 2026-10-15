from dataclasses import dataclass

from bot.db.repos import Repos
from bot.services.project_service import ProjectService


@dataclass
class Services:
    projects: ProjectService

    @classmethod
    def build(cls, repos: Repos) -> "Services":
        return cls(projects=ProjectService(repos))
