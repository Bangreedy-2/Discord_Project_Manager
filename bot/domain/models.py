from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID


class ProjectStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    BROKEN = "broken"
    DELETING = "deleting"


class Tier(StrEnum):
    OWNER = "owner"
    MEMBER = "member"
    VIEWER = "viewer"


class ChannelKind(StrEnum):
    TEXT = "text"
    VOICE = "voice"
    FORUM = "forum"


@dataclass(frozen=True)
class Project:
    id: UUID
    guild_id: int
    name: str
    creator_id: int
    status: ProjectStatus
    category_id: int | None
    owner_role_id: int | None
    member_role_id: int | None
    viewer_role_id: int | None
    created_at: datetime

    @classmethod
    def from_record(cls, r: Any) -> "Project":
        return cls(
            id=r["id"],
            guild_id=r["guild_id"],
            name=r["name"],
            creator_id=r["creator_id"],
            status=ProjectStatus(r["status"]),
            category_id=r["category_id"],
            owner_role_id=r["owner_role_id"],
            member_role_id=r["member_role_id"],
            viewer_role_id=r["viewer_role_id"],
            created_at=r["created_at"],
        )

    def role_id(self, tier: Tier) -> int | None:
        return {
            Tier.OWNER: self.owner_role_id,
            Tier.MEMBER: self.member_role_id,
            Tier.VIEWER: self.viewer_role_id,
        }[tier]

    @property
    def role_ids(self) -> tuple[int, ...]:
        return tuple(
            i for i in (self.owner_role_id, self.member_role_id, self.viewer_role_id) if i
        )


@dataclass(frozen=True)
class ProjectChannel:
    channel_id: int
    project_id: UUID
    kind: ChannelKind
    is_public: bool
    public_can_post: bool
    created_by: int
    created_at: datetime

    @classmethod
    def from_record(cls, r: Any) -> "ProjectChannel":
        return cls(
            channel_id=r["channel_id"],
            project_id=r["project_id"],
            kind=ChannelKind(r["kind"]),
            is_public=r["is_public"],
            public_can_post=r["public_can_post"],
            created_by=r["created_by"],
            created_at=r["created_at"],
        )


@dataclass(frozen=True)
class GuildSettings:
    guild_id: int
    max_projects_per_user: int = 3
    max_channels_per_proj: int = 15


@dataclass
class AuditEntry:
    guild_id: int
    actor_id: int
    action: str
    project_id: UUID | None = None
    target_id: int | None = None
    details: dict[str, Any] = field(default_factory=dict)
