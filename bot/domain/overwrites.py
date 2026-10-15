"""Pure permission builders. No API calls, so they can be unit-tested without Discord."""

from typing import Any

import discord

from bot.domain.models import Tier

P = discord.PermissionOverwrite

ROLE_MARKER = "◆"
MAX_NAME_LENGTH = 80


def role_name(project_name: str, tier: Tier) -> str:
    return f"{ROLE_MARKER} {project_name} · {tier.value.capitalize()}"


def owner_overwrite() -> discord.PermissionOverwrite:
    return P(
        view_channel=True, read_message_history=True,
        send_messages=True, send_messages_in_threads=True, add_reactions=True,
        create_public_threads=True, manage_messages=True,
        connect=True, speak=True,
    )


def member_overwrite() -> discord.PermissionOverwrite:
    return P(
        view_channel=True, read_message_history=True,
        send_messages=True, send_messages_in_threads=True, add_reactions=True,
        create_public_threads=True,
        connect=True, speak=True,
    )


def viewer_overwrite() -> discord.PermissionOverwrite:
    return P(
        view_channel=True, read_message_history=True,
        send_messages=False, send_messages_in_threads=False, add_reactions=False,
        create_public_threads=False,
        connect=True, speak=False,
    )


def bot_overwrite() -> discord.PermissionOverwrite:
    # No manage_roles: Discord only lets an Administrator allow it in an overwrite.
    # The bot's guild-level Manage Roles already covers editing these overwrites.
    return P(
        view_channel=True, read_message_history=True, send_messages=True,
        manage_messages=True, connect=True,
        manage_channels=True,
    )


def category_overwrites(
    guild: Any, owner: Any, member: Any, viewer: Any
) -> dict[Any, discord.PermissionOverwrite]:
    """Overwrites for a project's category; private channels inherit them by syncing."""
    return {
        guild.default_role: P(view_channel=False, connect=False),
        owner: owner_overwrite(),
        member: member_overwrite(),
        viewer: viewer_overwrite(),
        guild.me: bot_overwrite(),
    }


def public_everyone_overwrite(can_post: bool = False) -> discord.PermissionOverwrite:
    """@everyone overwrite added to a public channel on top of the category's overwrites."""
    return P(
        view_channel=True, read_message_history=True, connect=True,
        send_messages=can_post, send_messages_in_threads=can_post,
        add_reactions=can_post, create_public_threads=False, speak=can_post,
    )


def validate_project_name(name: str) -> str:
    """Return the cleaned name, or raise InvalidName."""
    from bot.errors import InvalidName

    cleaned = " ".join(name.split())
    if not cleaned:
        raise InvalidName("Project name can't be empty.")
    if len(cleaned) > MAX_NAME_LENGTH:
        raise InvalidName(f"Project name must be at most {MAX_NAME_LENGTH} characters.")
    if ROLE_MARKER in cleaned or "@" in cleaned or "#" in cleaned:
        raise InvalidName(f"Project name can't contain `{ROLE_MARKER}`, `@` or `#`.")
    return cleaned
