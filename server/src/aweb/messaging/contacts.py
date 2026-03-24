from __future__ import annotations

import re
from uuid import UUID

from aweb.service_errors import ConflictError, ValidationError

CONTACT_ADDRESS_PATTERN = re.compile(r"^[a-zA-Z0-9/_.-]+$")


async def add_contact(
    db,
    *,
    project_id: str,
    contact_address: str,
    label: str | None,
) -> dict:
    """Add a contact to the project. Returns the created contact dict.

    Raises ServiceError subclasses on validation failure or conflict.
    """
    aweb_db = db.get_manager("aweb")

    addr = contact_address.strip()
    if not addr or not CONTACT_ADDRESS_PATTERN.match(addr):
        raise ValidationError("Invalid contact_address format")

    row = await aweb_db.fetch_one(
        """
        INSERT INTO {{tables.contacts}} (project_id, contact_address, label)
        VALUES ($1, $2, $3)
        ON CONFLICT (project_id, contact_address) DO NOTHING
        RETURNING contact_id, contact_address, label, created_at
        """,
        UUID(project_id),
        addr,
        label,
    )
    if row is None:
        raise ConflictError("Contact already exists")

    return {
        "contact_id": str(row["contact_id"]),
        "contact_address": row["contact_address"],
        "label": row["label"],
        "created_at": row["created_at"].isoformat(),
    }


async def list_contacts(db, *, project_id: str) -> list[dict]:
    """List all contacts for a project."""
    aweb_db = db.get_manager("aweb")

    rows = await aweb_db.fetch_all(
        """
        SELECT contact_id, contact_address, label, created_at
        FROM {{tables.contacts}}
        WHERE project_id = $1
        ORDER BY contact_address
        """,
        UUID(project_id),
    )

    return [
        {
            "contact_id": str(r["contact_id"]),
            "contact_address": r["contact_address"],
            "label": r["label"],
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]


async def get_contact_addresses(db, *, project_id: str) -> set[str]:
    """Return all contact_address values for a project."""
    aweb_db = db.get_manager("aweb")
    rows = await aweb_db.fetch_all(
        "SELECT contact_address FROM {{tables.contacts}} WHERE project_id = $1",
        UUID(project_id),
    )
    return {r["contact_address"] for r in rows}


def is_address_in_contacts(address: str, contact_addresses: set[str]) -> bool:
    """Check if an address matches any contact (exact or project/domain-level).

    Supports two cross-boundary address formats:
    - Local cross-project: ``project_slug~alias`` (tilde separator)
    - DNS: ``domain/name`` (slash separator)

    Project/domain-level matching: adding ``org-beta`` as a contact matches
    ``org-beta~alice``; adding ``example.com`` matches ``example.com/alice``.
    """
    if address in contact_addresses:
        return True
    # Local cross-project match: "project~alias" → check "project"
    tilde = address.rfind("~")
    if tilde > 0:
        return address[:tilde] in contact_addresses
    # DNS address match: "domain.com/name" → check "domain.com"
    slash = address.rfind("/")
    if slash > 0:
        return address[:slash] in contact_addresses
    return False


async def remove_contact(db, *, project_id: str, contact_id: str) -> None:
    """Remove a contact by ID. Idempotent (no error if not found).

    Raises ValidationError on invalid contact_id format.
    """
    try:
        contact_uuid = UUID(contact_id.strip())
    except Exception:
        raise ValidationError("Invalid contact_id format")

    aweb_db = db.get_manager("aweb")
    await aweb_db.execute(
        "DELETE FROM {{tables.contacts}} WHERE contact_id = $1 AND project_id = $2",
        contact_uuid,
        UUID(project_id),
    )


async def check_access(
    db,
    *,
    target_project_id: str,
    target_agent_id: str,
    sender_project_id: str,
    sender_address: str,
    sender_owner_type: str | None = None,
    sender_owner_ref: str | None = None,
) -> bool:
    """Check whether a sender is allowed to reach the target agent.

    Returns True if:
    - Target agent's access_mode is 'open', OR
    - Sender is in the same project as target, OR
    - Target agent is owner-only and sender belongs to the same owner, OR
    - Target agent is contacts-only and sender's address is in target project's contacts.
    """
    aweb_db = db.get_manager("aweb")

    # 1. Fetch target agent's access_mode.
    row = await aweb_db.fetch_one(
        """
        SELECT a.access_mode, p.owner_type, p.owner_ref
        FROM {{tables.agents}} a
        JOIN {{tables.projects}} p ON p.project_id = a.project_id
        WHERE a.agent_id = $1 AND a.project_id = $2 AND a.deleted_at IS NULL
        """,
        UUID(target_agent_id),
        UUID(target_project_id),
    )
    if row is None:
        return False

    if row["access_mode"] == "open":
        return True

    # 2. Same-project bypass.
    if sender_project_id == target_project_id:
        return True

    if row["access_mode"] == "project_only":
        return False

    if row["access_mode"] == "owner_only":
        target_owner_type = row.get("owner_type")
        target_owner_ref = str(row.get("owner_ref")) if row.get("owner_ref") is not None else None
        return bool(
            sender_owner_type
            and sender_owner_ref
            and target_owner_type
            and target_owner_ref
            and sender_owner_type == target_owner_type
            and sender_owner_ref == target_owner_ref
        )

    # 3. Check contacts for exact or project/domain-level match.
    contacts = await get_contact_addresses(db, project_id=target_project_id)
    return is_address_in_contacts(sender_address, contacts)
