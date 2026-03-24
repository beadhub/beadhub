"""Assigned-address continuity metadata for outgoing deliveries."""

from __future__ import annotations

from uuid import UUID


async def get_sender_delivery_metadata(
    aweb_db,
    *,
    sender_ids: list[UUID],
) -> dict[str, dict]:
    if not sender_ids:
        return {}

    rows = await aweb_db.fetch_all(
        """
        SELECT DISTINCT ON (a.agent_id)
            a.agent_id,
            ns.domain,
            pa.name,
            ra.old_did,
            ra.new_did,
            ra.controller_did,
            ra.replacement_timestamp,
            ra.controller_signature
        FROM {{tables.agents}} a
        LEFT JOIN {{tables.public_addresses}} pa
          ON pa.did_aw = a.stable_id
         AND pa.deleted_at IS NULL
        LEFT JOIN {{tables.dns_namespaces}} ns
          ON ns.namespace_id = pa.namespace_id
         AND ns.deleted_at IS NULL
        LEFT JOIN {{tables.replacement_announcements}} ra
          ON ra.new_agent_id = a.agent_id
         AND ra.namespace_id = pa.namespace_id
         AND ra.address_name = pa.name
        WHERE a.agent_id = ANY($1::uuid[])
          AND a.deleted_at IS NULL
        ORDER BY a.agent_id, ns.domain ASC NULLS LAST, pa.name ASC NULLS LAST, ra.created_at DESC NULLS LAST
        """,
        sender_ids,
    )

    result: dict[str, dict] = {}
    for row in rows:
        address = None
        if row.get("domain") and row.get("name"):
            address = f"{row['domain']}/{row['name']}"
        replacement = None
        if address and row.get("old_did") and row.get("new_did") and row.get("controller_signature"):
            replacement = {
                "address": address,
                "old_did": row["old_did"],
                "new_did": row["new_did"],
                "controller_did": row["controller_did"],
                "timestamp": row["replacement_timestamp"],
                "controller_signature": row["controller_signature"],
            }
        result[str(row["agent_id"])] = {
            "from_address": address,
            "replacement_announcement": replacement,
        }
    return result
