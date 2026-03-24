from __future__ import annotations

ADDRESS_REACHABILITY_VALUES = {
    "private",
    "org_visible",
    "contacts_only",
    "public",
}


def normalize_address_reachability(value: str | None, *, default: str = "private") -> str:
    normalized = (value or "").strip().lower().replace("-", "_") or default
    if normalized not in ADDRESS_REACHABILITY_VALUES:
        raise ValueError(
            f"address_reachability must be one of {sorted(ADDRESS_REACHABILITY_VALUES)}"
        )
    return normalized
