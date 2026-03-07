"""Notification outbox pattern for reliable delivery.

This module implements the outbox pattern to ensure notifications are:
1. Recorded atomically (as close as possible to the triggering event)
2. Delivered reliably with retry capability
3. Tracked for observability
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import TYPE_CHECKING, List
from uuid import UUID

import asyncpg.exceptions
from aweb.messages_service import deliver_message

if TYPE_CHECKING:
    from .beads_sync import BeadStatusChange
    from .db import DatabaseInfra

logger = logging.getLogger(__name__)

MAX_RETRY_ATTEMPTS = 3
SYSTEM_SENDER_ALIAS = "system"
SYSTEM_SENDER_HUMAN_NAME = "BeadHub Notifications"


async def ensure_system_sender(db_infra: "DatabaseInfra", project_id: str) -> tuple[str, str]:
    """Ensure a per-project system agent exists and return (agent_id, alias).

    Uses a deterministic UUID derived from the project_id so the same
    system agent is reused across calls without extra lookups.
    """
    agent_id = uuid.uuid5(uuid.NAMESPACE_URL, f"beadhub:system:{project_id}")
    aweb_db = db_infra.get_manager("aweb")

    # Fast path: agent already exists (cheap PK lookup).
    row = await aweb_db.fetch_one(
        "SELECT agent_id FROM {{tables.agents}} WHERE agent_id = $1 AND deleted_at IS NULL",
        agent_id,
    )
    if row:
        return str(agent_id), SYSTEM_SENDER_ALIAS

    try:
        await aweb_db.execute(
            """
            INSERT INTO {{tables.agents}}
                (agent_id, project_id, alias, human_name, agent_type,
                 lifetime, status, custody)
            VALUES ($1, $2, $3, $4, 'system', 'persistent', 'active', 'custodial')
            ON CONFLICT (agent_id) DO NOTHING
            """,
            agent_id,
            UUID(project_id),
            SYSTEM_SENDER_ALIAS,
            SYSTEM_SENDER_HUMAN_NAME,
        )
    except asyncpg.exceptions.UniqueViolationError:
        raise RuntimeError(
            f"Cannot create system notification sender for project {project_id}: "
            f"alias '{SYSTEM_SENDER_ALIAS}' is already taken by another agent. "
            f"Rename the conflicting agent to restore notifications."
        )
    return str(agent_id), SYSTEM_SENDER_ALIAS


async def record_notification_intents(
    status_changes: List["BeadStatusChange"],
    project_id: str,
    db_infra: "DatabaseInfra",
) -> int:
    """Record notification intents in the outbox for later processing.

    This should be called immediately after the triggering event commits.
    Each status change that has subscribers will get an outbox entry.

    Args:
        status_changes: List of bead status changes to notify about
        project_id: Project UUID for tenant isolation
        db_infra: Database infrastructure

    Returns:
        Number of outbox entries created
    """
    from .routes.subscriptions import get_subscribers_for_bead

    server_db = db_infra.get_manager("server")
    entries_created = 0

    for change in status_changes:
        # Skip notifications for new issues (no old_status)
        if change.old_status is None:
            continue

        # Get subscribers for this bead
        subscribers = await get_subscribers_for_bead(
            db_infra=db_infra,
            project_id=project_id,
            bead_id=change.bead_id,
            event_type="status_change",
            repo=change.repo,
        )

        if not subscribers:
            continue

        # Build notification payload
        payload = {
            "bead_id": change.bead_id,
            "repo": change.repo,
            "branch": change.branch,
            "old_status": change.old_status,
            "new_status": change.new_status,
            "title": change.title,
        }

        # Create outbox entry for each subscriber
        for sub in subscribers:
            await server_db.execute(
                """
                INSERT INTO {{tables.notification_outbox}}
                    (project_id, event_type, payload, recipient_workspace_id, recipient_alias)
                VALUES ($1, $2, $3, $4, $5)
                """,
                project_id,
                "bead_status_change",
                json.dumps(payload),
                sub["workspace_id"],
                sub["alias"],
            )
            entries_created += 1

    return entries_created


async def process_notification_outbox(
    project_id: str,
    db_infra: "DatabaseInfra",
    *,
    limit: int = 100,
) -> tuple[int, int]:
    """Process pending notifications from the outbox.

    Uses a per-project system sender so notifications are never self-sent.

    Returns:
        Tuple of (sent_count, failed_count)
    """
    sender_agent_id, sender_alias = await ensure_system_sender(db_infra, project_id)
    server_db = db_infra.get_manager("server")
    sent_count = 0
    failed_count = 0

    # Fetch candidate entries (no row lock — just identifies work to do).
    candidates = await server_db.fetch_all(
        """
        SELECT id, payload, recipient_workspace_id, recipient_alias, attempts
        FROM {{tables.notification_outbox}}
        WHERE project_id = $1
          AND status IN ('pending', 'failed')
          AND attempts < $2
        ORDER BY created_at ASC
        LIMIT $3
        """,
        project_id,
        MAX_RETRY_ATTEMPTS,
        limit,
    )

    for candidate in candidates:
        outbox_id = candidate["id"]

        # Per-entry transaction: claim with FOR UPDATE SKIP LOCKED, process,
        # and update status atomically. Concurrent processors skip locked rows.
        async with server_db.transaction() as tx:
            locked = await tx.fetch_one(
                """
                SELECT id, payload, recipient_workspace_id, attempts
                FROM {{tables.notification_outbox}}
                WHERE id = $1 AND status IN ('pending', 'failed')
                FOR UPDATE SKIP LOCKED
                """,
                outbox_id,
            )
            if locked is None:
                continue  # Already claimed by another processor

            payload = locked["payload"]
            recipient_workspace_id = str(locked["recipient_workspace_id"])
            attempts = locked["attempts"] + 1

            if isinstance(payload, str):
                payload = json.loads(payload)

            # Mark as processing
            await tx.execute(
                """
                UPDATE {{tables.notification_outbox}}
                SET status = 'processing', attempts = $2
                WHERE id = $1
                """,
                outbox_id,
                attempts,
            )

            try:
                # Skip sending to deleted/missing workspaces.
                recipient_row = await tx.fetch_one(
                    """
                    SELECT deleted_at
                    FROM {{tables.workspaces}}
                    WHERE workspace_id = $1 AND project_id = $2
                    """,
                    UUID(recipient_workspace_id),
                    UUID(project_id),
                )
                if not recipient_row or recipient_row.get("deleted_at") is not None:
                    raise RuntimeError("Recipient workspace not found or deleted")

                # Build notification message
                bead_id = payload.get("bead_id", "unknown")
                old_status = payload.get("old_status", "unknown")
                new_status = payload.get("new_status", "unknown")
                title = payload.get("title", "")
                repo = payload.get("repo", "")
                branch = payload.get("branch", "")

                subject = f"Bead status changed: {bead_id}"
                body = f"**{bead_id}** status changed" f" from `{old_status}` to `{new_status}`\n\n"
                if title:
                    body += f"Title: {title}\n"
                if repo:
                    body += f"Repo: {repo}\n"
                if branch:
                    body += f"Branch: {branch}\n"

                # Generate deterministic thread ID for this bead
                thread_uuid = uuid.uuid5(uuid.NAMESPACE_URL, f"bead:{bead_id}")

                message_id, _created_at = await deliver_message(
                    db_infra,
                    project_id=project_id,
                    from_agent_id=sender_agent_id,
                    from_alias=sender_alias,
                    to_agent_id=recipient_workspace_id,
                    subject=subject,
                    body=body,
                    priority="normal",
                    thread_id=str(thread_uuid),
                )

                # Mark as completed (within the same transaction)
                await tx.execute(
                    """
                    UPDATE {{tables.notification_outbox}}
                    SET status = 'completed',
                        processed_at = NOW(),
                        message_id = $2,
                        last_error = NULL
                    WHERE id = $1
                    """,
                    outbox_id,
                    message_id,
                )
                sent_count += 1

            except Exception as e:
                logger.exception(
                    "Failed to send notification for outbox entry %s (attempt %d)",
                    outbox_id,
                    attempts,
                )
                error_msg = str(e)[:500]
                await tx.execute(
                    """
                    UPDATE {{tables.notification_outbox}}
                    SET status = 'failed',
                        last_error = $2
                    WHERE id = $1
                    """,
                    outbox_id,
                    error_msg,
                )
                failed_count += 1

    return sent_count, failed_count


async def cleanup_old_notifications(
    db_infra: "DatabaseInfra",
    project_id: str,
    days_old: int = 7,
) -> int:
    """Delete old completed notifications from the outbox.

    Args:
        db_infra: Database infrastructure
        project_id: Project UUID for tenant isolation
        days_old: Delete completed entries older than this many days

    Returns:
        Number of entries deleted
    """
    server_db = db_infra.get_manager("server")

    result = await server_db.fetch_value(
        """
        WITH deleted AS (
            DELETE FROM {{tables.notification_outbox}}
            WHERE project_id = $1
              AND status = 'completed'
              AND processed_at < NOW() - INTERVAL '1 day' * $2
            RETURNING id
        )
        SELECT COUNT(*) FROM deleted
        """,
        project_id,
        days_old,
    )
    return int(result or 0)
