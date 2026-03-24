"""Database helpers for stable identity (did:aw) backfill and lookup."""

from __future__ import annotations

from uuid import UUID

from aweb.awid.did import stable_id_from_did_key, validate_stable_id


async def ensure_agent_stable_ids(
    aweb_db, *, project_id: str | None = None, agent_ids: list[str]
) -> dict[str, str]:
    if not agent_ids:
        return {}

    ids = [UUID(a) for a in agent_ids]

    if project_id is not None:
        project_uuid = UUID(project_id)
        rows = await aweb_db.fetch_all(
            """
            SELECT
                a.agent_id,
                a.project_id,
                a.stable_id,
                a.lifetime,
                COALESCE(l.new_did, a.did) AS initial_did
            FROM {{tables.agents}} a
            LEFT JOIN LATERAL (
                SELECT new_did
                FROM {{tables.agent_log}}
                WHERE agent_id = a.agent_id AND operation IN ('create', 'claim_identity')
                ORDER BY created_at ASC
                LIMIT 1
            ) l ON TRUE
            WHERE a.project_id = $1
              AND a.agent_id = ANY($2::uuid[])
              AND a.deleted_at IS NULL
            """,
            project_uuid,
            ids,
        )
    else:
        rows = await aweb_db.fetch_all(
            """
            SELECT
                a.agent_id,
                a.project_id,
                a.stable_id,
                a.lifetime,
                COALESCE(l.new_did, a.did) AS initial_did
            FROM {{tables.agents}} a
            LEFT JOIN LATERAL (
                SELECT new_did
                FROM {{tables.agent_log}}
                WHERE agent_id = a.agent_id AND operation IN ('create', 'claim_identity')
                ORDER BY created_at ASC
                LIMIT 1
            ) l ON TRUE
            WHERE a.agent_id = ANY($1::uuid[])
              AND a.deleted_at IS NULL
            """,
            ids,
        )

    stable_by_id: dict[str, str] = {}
    to_update: list[tuple[UUID, str]] = []
    for r in rows:
        agent_id = str(r["agent_id"])
        stable = r.get("stable_id")
        if stable:
            try:
                stable_by_id[agent_id] = validate_stable_id(stable)
            except Exception:
                pass
            continue
        if (r.get("lifetime") or "ephemeral") != "persistent":
            continue
        initial_did = r.get("initial_did")
        if not initial_did:
            continue
        try:
            stable = stable_id_from_did_key(initial_did)
        except Exception:
            continue
        stable_by_id[agent_id] = stable
        to_update.append((UUID(agent_id), stable))

    for agent_uuid, stable in to_update:
        row_project_id = next(
            (UUID(str(r["project_id"])) for r in rows if str(r["agent_id"]) == str(agent_uuid)),
            None,
        )
        if row_project_id is None:
            continue
        await aweb_db.execute(
            """
            UPDATE {{tables.agents}}
            SET stable_id = $1
            WHERE agent_id = $2 AND project_id = $3 AND stable_id IS NULL
            """,
            stable,
            agent_uuid,
            row_project_id,
        )

    return stable_by_id


async def backfill_missing_stable_ids(aweb_db, *, batch_size: int = 500) -> int:
    updated = 0
    while True:
        rows = await aweb_db.fetch_all(
            """
            SELECT
                a.agent_id,
                a.project_id,
                COALESCE(l.new_did, a.did) AS initial_did
            FROM {{tables.agents}} a
            LEFT JOIN LATERAL (
                SELECT new_did
                FROM {{tables.agent_log}}
                WHERE agent_id = a.agent_id AND operation IN ('create', 'claim_identity')
                ORDER BY created_at ASC
                LIMIT 1
            ) l ON TRUE
            WHERE a.deleted_at IS NULL
              AND a.stable_id IS NULL
              AND a.lifetime = 'persistent'
              AND a.did IS NOT NULL
            LIMIT $1
            """,
            int(batch_size),
        )
        if not rows:
            break

        updated_this_batch = 0
        for r in rows:
            agent_id = r["agent_id"]
            project_id = r["project_id"]
            initial_did = r.get("initial_did")
            if not initial_did:
                continue
            try:
                stable = stable_id_from_did_key(initial_did)
            except Exception:
                continue
            await aweb_db.execute(
                """
                UPDATE {{tables.agents}}
                SET stable_id = $1
                WHERE agent_id = $2 AND project_id = $3 AND stable_id IS NULL
                """,
                stable,
                UUID(str(agent_id)),
                UUID(str(project_id)),
            )
            updated_this_batch += 1
            updated += 1

        if updated_this_batch == 0:
            break

    return updated
