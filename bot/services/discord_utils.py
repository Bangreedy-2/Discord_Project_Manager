import logging
from typing import Any

import discord

log = logging.getLogger(__name__)


async def safe_delete(obj: Any, reason: str | None = None) -> bool:
    """Delete a Discord object, ignoring it if it's already gone. Returns True if deleted."""
    if obj is None:
        return False
    try:
        await obj.delete(reason=reason)
        return True
    except discord.NotFound:
        return False
    except discord.HTTPException:
        log.exception("failed to delete %r", obj)
        return False
