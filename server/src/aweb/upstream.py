"""Helpers for translating embedded-client errors inside the OSS package."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException


def upstream_error_to_http_exception(exc: Exception, *, prefix: str = "aweb") -> HTTPException:
    status_code = int(getattr(exc, "status_code", 503))
    message = str(getattr(exc, "message", str(exc)))
    details: Any = getattr(exc, "details", None)
    detail: Any = message
    if details is not None:
        detail = {
            "source": prefix,
            "message": message,
            "details": details,
        }
    return HTTPException(status_code=status_code, detail=detail)


def is_upstream_client_error(exc: Exception) -> bool:
    return hasattr(exc, "status_code") and hasattr(exc, "message")
