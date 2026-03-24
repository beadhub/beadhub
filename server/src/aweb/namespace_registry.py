from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from uuid import UUID

import asyncpg

from aweb.address_reachability import normalize_address_reachability


SUBDOMAIN_LABEL_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
AGENT_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")


def validate_subdomain_label(value: str) -> str:
    label = (value or "").strip().lower()
    if not label:
        raise ValueError("Subnamespace label is required")
    if not SUBDOMAIN_LABEL_PATTERN.fullmatch(label):
        raise ValueError(
            "Subnamespace label must contain only lowercase letters, digits, or hyphens"
        )
    return label


def validate_agent_name(value: str) -> str:
    name = (value or "").strip().lower()
    if not name:
        raise ValueError("Agent name is required")
    if len(name) > 64:
        raise ValueError("Agent name must be 64 characters or fewer")
    if not AGENT_NAME_PATTERN.fullmatch(name):
        raise ValueError(
            "Agent name must start with an alphanumeric character and contain only letters, digits, hyphens, or underscores"
        )
    return name


def _normalize_domain(domain: str) -> str:
    value = (domain or "").strip().lower().rstrip(".")
    if not value:
        raise ValueError("Domain is required")
    if len(value) > 256:
        raise ValueError("Domain is too long")
    return value


def _address_record(row, *, domain: str) -> dict:
    return {
        "address_id": str(row["address_id"]),
        "domain": domain,
        "name": str(row["name"]),
        "did_aw": str(row["did_aw"]),
        "current_did_key": str(row["current_did_key"]),
        "reachability": str(row.get("reachability") or "private"),
        "created_at": row["created_at"].isoformat(),
        "address": f"{domain}/{row['name']}",
    }


def _namespace_record(row) -> dict:
    return {
        "namespace_id": str(row["namespace_id"]),
        "domain": str(row["domain"]),
        "controller_did": str(row["controller_did"]) if row.get("controller_did") else None,
        "verification_status": str(row["verification_status"]),
        "last_verified_at": row["last_verified_at"].isoformat() if row.get("last_verified_at") else None,
        "created_at": row["created_at"].isoformat(),
        "namespace_type": str(row.get("namespace_type") or "dns_verified"),
        "scope_id": str(row["scope_id"]) if row.get("scope_id") else None,
    }


async def get_namespace(*, aweb_db, domain: str) -> dict | None:
    normalized = _normalize_domain(domain)
    row = await aweb_db.fetch_one(
        """
        SELECT namespace_id, domain, controller_did, verification_status,
               last_verified_at, created_at, namespace_type, scope_id
        FROM {{tables.dns_namespaces}}
        WHERE domain = $1 AND deleted_at IS NULL
        """,
        normalized,
    )
    return _namespace_record(row) if row is not None else None


async def ensure_dns_namespace_registered(
    *,
    aweb_db,
    domain: str,
    controller_did: str | None,
    namespace_type: str = "dns_verified",
    scope_id: str | None = None,
) -> dict:
    normalized = _normalize_domain(domain)
    now = datetime.now(timezone.utc)
    scope_uuid = UUID(scope_id) if scope_id else None

    row = await aweb_db.fetch_one(
        """
        SELECT namespace_id
        FROM {{tables.dns_namespaces}}
        WHERE domain = $1 AND deleted_at IS NULL
        """,
        normalized,
    )
    if row is None:
        created = await aweb_db.fetch_one(
            """
            INSERT INTO {{tables.dns_namespaces}}
                (namespace_id, domain, controller_did, namespace_type, scope_id,
                 verification_status, last_verified_at, created_at)
            VALUES ($1, $2, $3, $4, $5, 'verified', $6, $6)
            RETURNING namespace_id, domain, controller_did, verification_status,
                      last_verified_at, created_at, namespace_type, scope_id
            """,
            uuid.uuid4(),
            normalized,
            controller_did,
            namespace_type,
            scope_uuid,
            now,
        )
        if created is None:
            raise RuntimeError("Failed to register namespace")
        return _namespace_record(created)

    updated = await aweb_db.fetch_one(
        """
        UPDATE {{tables.dns_namespaces}}
        SET controller_did = $2,
            namespace_type = $3,
            scope_id = $4,
            verification_status = 'verified',
            last_verified_at = $5,
            deleted_at = NULL
        WHERE domain = $1 AND deleted_at IS NULL
        RETURNING namespace_id, domain, controller_did, verification_status,
                  last_verified_at, created_at, namespace_type, scope_id
        """,
        normalized,
        controller_did,
        namespace_type,
        scope_uuid,
        now,
    )
    if updated is None:
        raise RuntimeError("Failed to refresh namespace registration")
    return _namespace_record(updated)


async def get_namespace_address(*, aweb_db, domain: str, name: str) -> dict | None:
    namespace = await get_namespace(aweb_db=aweb_db, domain=domain)
    if namespace is None:
        return None
    row = await aweb_db.fetch_one(
        """
        SELECT address_id, name, did_aw, current_did_key, reachability, created_at
        FROM {{tables.public_addresses}}
        WHERE namespace_id = $1 AND name = $2 AND deleted_at IS NULL
        """,
        UUID(namespace["namespace_id"]),
        name,
    )
    return _address_record(row, domain=namespace["domain"]) if row is not None else None


async def list_namespace_addresses(*, aweb_db, domain: str) -> list[dict]:
    namespace = await get_namespace(aweb_db=aweb_db, domain=domain)
    if namespace is None:
        return []
    rows = await aweb_db.fetch_all(
        """
        SELECT address_id, name, did_aw, current_did_key, reachability, created_at
        FROM {{tables.public_addresses}}
        WHERE namespace_id = $1 AND deleted_at IS NULL
        ORDER BY name
        """,
        UUID(namespace["namespace_id"]),
    )
    return [_address_record(row, domain=namespace["domain"]) for row in rows]


async def register_namespace_address(
    *,
    aweb_db,
    domain: str,
    name: str,
    did_aw: str,
    current_did_key: str,
    reachability: str = "private",
) -> dict:
    namespace = await get_namespace(aweb_db=aweb_db, domain=domain)
    if namespace is None:
        raise ValueError("Namespace not found")
    reachability = normalize_address_reachability(reachability)
    try:
        row = await aweb_db.fetch_one(
            """
            INSERT INTO {{tables.public_addresses}}
                (address_id, namespace_id, name, did_aw, current_did_key, reachability, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING address_id, name, did_aw, current_did_key, reachability, created_at
            """,
            uuid.uuid4(),
            UUID(namespace["namespace_id"]),
            name,
            did_aw,
            current_did_key,
            reachability,
            datetime.now(timezone.utc),
        )
    except asyncpg.UniqueViolationError as exc:
        raise ValueError("Address name already registered") from exc
    if row is None:
        raise RuntimeError("Failed to register address")
    return _address_record(row, domain=namespace["domain"])


async def reassign_namespace_address(
    *,
    aweb_db,
    domain: str,
    name: str,
    did_aw: str,
    current_did_key: str,
    reachability: str | None = None,
) -> dict:
    namespace = await get_namespace(aweb_db=aweb_db, domain=domain)
    if namespace is None:
        raise ValueError("Namespace not found")
    if reachability is None:
        row = await aweb_db.fetch_one(
            """
            UPDATE {{tables.public_addresses}}
            SET did_aw = $3,
                current_did_key = $4
            WHERE namespace_id = $1
              AND name = $2
              AND deleted_at IS NULL
            RETURNING address_id, name, did_aw, current_did_key, reachability, created_at
            """,
            UUID(namespace["namespace_id"]),
            name,
            did_aw,
            current_did_key,
        )
    else:
        normalized = normalize_address_reachability(reachability)
        row = await aweb_db.fetch_one(
            """
            UPDATE {{tables.public_addresses}}
            SET did_aw = $3,
                current_did_key = $4,
                reachability = $5
            WHERE namespace_id = $1
              AND name = $2
              AND deleted_at IS NULL
            RETURNING address_id, name, did_aw, current_did_key, reachability, created_at
            """,
            UUID(namespace["namespace_id"]),
            name,
            did_aw,
            current_did_key,
            normalized,
        )
    if row is None:
        raise ValueError("Address not found")
    return _address_record(row, domain=namespace["domain"])


async def set_namespace_address_reachability(
    *,
    aweb_db,
    domain: str,
    name: str,
    reachability: str,
) -> dict:
    namespace = await get_namespace(aweb_db=aweb_db, domain=domain)
    if namespace is None:
        raise ValueError("Namespace not found")
    normalized = normalize_address_reachability(reachability)
    row = await aweb_db.fetch_one(
        """
        UPDATE {{tables.public_addresses}}
        SET reachability = $3
        WHERE namespace_id = $1
          AND name = $2
          AND deleted_at IS NULL
        RETURNING address_id, name, did_aw, current_did_key, reachability, created_at
        """,
        UUID(namespace["namespace_id"]),
        name,
        normalized,
    )
    if row is None:
        raise ValueError("Address not found")
    return _address_record(row, domain=namespace["domain"])


async def delete_namespace_address(*, aweb_db, domain: str, name: str) -> bool:
    namespace = await get_namespace(aweb_db=aweb_db, domain=domain)
    if namespace is None:
        return False
    result = await aweb_db.execute(
        """
        UPDATE {{tables.public_addresses}}
        SET deleted_at = NOW()
        WHERE namespace_id = $1
          AND name = $2
          AND deleted_at IS NULL
        """,
        UUID(namespace["namespace_id"]),
        name,
    )
    return not result.startswith("UPDATE 0")

