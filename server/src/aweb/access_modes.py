from __future__ import annotations

VALID_ACCESS_MODES = {"project_only", "owner_only", "contacts_only", "open"}


def validate_access_mode(value: str | None, *, default: str = "open") -> str:
    normalized = (value or default).strip() or default
    if normalized not in VALID_ACCESS_MODES:
        raise ValueError(f"access_mode must be one of {sorted(VALID_ACCESS_MODES)}")
    return normalized
