"""Translate aweb mutation hooks into beadhub SSE events.

aweb fires app.state.on_mutation(event_type, context) after successful
mutations. This module registers a handler that publishes corresponding
Event dataclasses to Redis pub/sub for the dashboard SSE stream.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

from redis.asyncio import Redis

from .events import (
    ChatMessageEvent,
    Event,
    MessageAcknowledgedEvent,
    MessageDeliveredEvent,
    ReservationAcquiredEvent,
    ReservationReleasedEvent,
    publish_event,
)
from .presence import get_agent_presence, get_workspace_project_slug

if TYPE_CHECKING:
    from .db import DatabaseInfra

logger = logging.getLogger(__name__)


def create_mutation_handler(redis: Redis, db_infra: DatabaseInfra):
    """Create an on_mutation callback that publishes SSE events.

    The returned async callable matches aweb's hook signature:
        async def on_mutation(event_type: str, context: dict) -> None
    """

    async def on_mutation(event_type: str, context: dict) -> None:
        try:
            event = _translate(event_type, context)
            if event is None:
                return
            if not event.workspace_id:
                logger.warning("Skipping %s event: no workspace_id in context", event_type)
                return
            try:
                await _enrich(event, redis, db_infra)
            except Exception:
                logger.warning(
                    "Enrichment failed for %s, publishing with defaults", event_type, exc_info=True
                )
            await publish_event(redis, event)
        except Exception:
            logger.warning("Failed to publish event for %s", event_type, exc_info=True)

    return on_mutation


async def _alias_for(redis: Redis, workspace_id: str) -> str:
    """Resolve alias from Redis presence. Returns empty string if unavailable."""
    presence = await get_agent_presence(redis, workspace_id)
    if presence is None:
        return ""
    return presence.get("alias", "")


async def _enrich(event: Event, redis: Redis, db_infra: DatabaseInfra) -> None:
    """Add aliases, subjects, and previews via Redis/DB lookups."""

    if isinstance(event, MessageDeliveredEvent):
        event.from_alias = await _alias_for(redis, event.from_workspace)
        event.to_alias = await _alias_for(redis, event.workspace_id)
        event.project_slug = await get_workspace_project_slug(redis, event.workspace_id)

    elif isinstance(event, MessageAcknowledgedEvent):
        if event.message_id:
            aweb_db = db_infra.get_manager("aweb")
            row = await aweb_db.fetch_one(
                "SELECT from_alias, subject FROM {{tables.messages}} WHERE message_id = $1",
                UUID(event.message_id),
            )
            if row:
                event.from_alias = row["from_alias"]
                event.subject = row["subject"] or ""
        event.project_slug = await get_workspace_project_slug(redis, event.workspace_id)

    elif isinstance(event, ChatMessageEvent):
        event.from_alias = await _alias_for(redis, event.workspace_id)
        aweb_db = db_infra.get_manager("aweb")
        if event.session_id and event.workspace_id:
            participants = await aweb_db.fetch_all(
                "SELECT alias FROM {{tables.chat_session_participants}} "
                "WHERE session_id = $1 AND agent_id != $2",
                UUID(event.session_id),
                UUID(event.workspace_id),
            )
            event.to_aliases = [r["alias"] for r in participants]
        if event.message_id:
            msg = await aweb_db.fetch_one(
                "SELECT body FROM {{tables.chat_messages}} WHERE message_id = $1",
                UUID(event.message_id),
            )
            if msg and msg["body"]:
                event.preview = msg["body"][:80]
        event.project_slug = await get_workspace_project_slug(redis, event.workspace_id)

    elif isinstance(event, (ReservationAcquiredEvent, ReservationReleasedEvent)):
        event.alias = await _alias_for(redis, event.workspace_id)
        event.project_slug = await get_workspace_project_slug(redis, event.workspace_id)


def _translate(event_type: str, ctx: dict):
    """Map an aweb mutation event to a beadhub Event dataclass."""

    if event_type == "message.sent":
        return MessageDeliveredEvent(
            workspace_id=ctx.get("to_agent_id", ""),
            message_id=ctx.get("message_id", ""),
            from_workspace=ctx.get("from_agent_id", ""),
            subject=ctx.get("subject", ""),
        )

    if event_type == "message.acknowledged":
        return MessageAcknowledgedEvent(
            workspace_id=ctx.get("agent_id", ""),
            message_id=ctx.get("message_id", ""),
        )

    if event_type == "chat.message_sent":
        return ChatMessageEvent(
            workspace_id=ctx.get("from_agent_id", ""),
            session_id=ctx.get("session_id", ""),
            message_id=ctx.get("message_id", ""),
        )

    if event_type == "reservation.acquired":
        return ReservationAcquiredEvent(
            workspace_id=ctx.get("holder_agent_id", ""),
            paths=[ctx["resource_key"]] if ctx.get("resource_key") else [],
            ttl_seconds=ctx.get("ttl_seconds", 0),
        )

    if event_type == "reservation.released":
        return ReservationReleasedEvent(
            workspace_id=ctx.get("holder_agent_id", ""),
            paths=[ctx["resource_key"]] if ctx.get("resource_key") else [],
        )

    return None
