from dataclasses import dataclass

import asyncpg

from bot.db.audit_repo import AuditRepo
from bot.db.channels_repo import ChannelsRepo
from bot.db.projects_repo import ProjectsRepo
from bot.db.settings_repo import SettingsRepo


@dataclass
class Repos:
    projects: ProjectsRepo
    channels: ChannelsRepo
    settings: SettingsRepo
    audit: AuditRepo

    @classmethod
    def from_pool(cls, pool: asyncpg.Pool) -> "Repos":
        return cls(
            projects=ProjectsRepo(pool),
            channels=ChannelsRepo(pool),
            settings=SettingsRepo(pool),
            audit=AuditRepo(pool),
        )
