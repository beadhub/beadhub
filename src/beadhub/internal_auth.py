from __future__ import annotations

import hashlib
import hmac
import logging
import os
import uuid
from typing import Optional, TypedDict

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

INTERNAL_AUTH_HEADER = "X-BH-Auth"
INTERNAL_PROJECT_HEADER = "X-Project-ID"
INTERNAL_USER_HEADER = "X-User-ID"
INTERNAL_API_KEY_ID_HEADER = "X-API-Key"
INTERNAL_ACTOR_ID_HEADER = "X-Aweb-Actor-ID"


class InternalAuthContext(TypedDict):
    project_id: str
    principal_type: str  # "u", "k", or "p"
    principal_id: str
    actor_id: str


def _get_internal_auth_secret() -> Optional[str]:
    # Some embedded/proxy deployments may reuse SESSION_SECRET_KEY to sign X-BH-Auth.
    # For standalone OSS this is typically unset.
    return os.getenv("BEADHUB_INTERNAL_AUTH_SECRET") or os.getenv("SESSION_SECRET_KEY")


def _internal_auth_header_value(
    *, secret: str, project_id: str, principal_type: str, principal_id: str, actor_id: str
) -> str:
    msg = f"v2:{project_id}:{principal_type}:{principal_id}:{actor_id}"
    sig = hmac.new(
        secret.encode("utf-8"),
        msg.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{msg}:{sig}"


def parse_internal_auth_context(request: Request) -> Optional[InternalAuthContext]:
    """Parse and validate proxy-injected auth context headers for BeadHub OSS.

    This is intended for proxy/wrapper deployments where the wrapper authenticates the caller
    (JWT/cookie/API key) and injects project scope to the core service.

    The core MUST treat these headers as untrusted unless `X-BH-Auth` validates.
    """
    internal_auth = request.headers.get(INTERNAL_AUTH_HEADER)
    if not internal_auth:
        return None

    # In standalone OSS mode the internal auth secret is intentionally unset. Treat any
    # client-supplied internal headers as untrusted and ignore them rather than
    # failing with a 500.
    secret = _get_internal_auth_secret()
    if not secret:
        path = request.scope.get("path") or ""
        logger.warning(
            "Ignoring %s header because BEADHUB_INTERNAL_AUTH_SECRET is not configured (path=%s)",
            INTERNAL_AUTH_HEADER,
            path,
        )
        return None

    project_id = request.headers.get(INTERNAL_PROJECT_HEADER)
    if not project_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        project_id = str(uuid.UUID(project_id))
    except ValueError:
        raise HTTPException(status_code=401, detail="Authentication required")

    user_id = request.headers.get(INTERNAL_USER_HEADER)
    api_key_id = request.headers.get(INTERNAL_API_KEY_ID_HEADER)
    if user_id:
        try:
            user_id = str(uuid.UUID(user_id))
        except ValueError:
            raise HTTPException(status_code=401, detail="Authentication required")
        principal_type = "u"
        principal_id = user_id
    elif api_key_id:
        try:
            api_key_id = str(uuid.UUID(api_key_id))
        except ValueError:
            raise HTTPException(status_code=401, detail="Authentication required")
        principal_type = "k"
        principal_id = api_key_id
    else:
        # No user or API key header — check if the signed auth header carries
        # a different principal type (e.g. "p" for public reader).
        parts = internal_auth.split(":")
        if len(parts) >= 5 and parts[0] == "v2" and parts[2] not in ("u", "k"):
            principal_type = parts[2]
            principal_id = parts[3]
        else:
            raise HTTPException(status_code=401, detail="Authentication required")

    actor_id = request.headers.get(INTERNAL_ACTOR_ID_HEADER)
    if not actor_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        actor_id = str(uuid.UUID(actor_id))
    except ValueError:
        raise HTTPException(status_code=401, detail="Authentication required")

    expected = _internal_auth_header_value(
        secret=secret,
        project_id=project_id,
        principal_type=principal_type,
        principal_id=principal_id,
        actor_id=actor_id,
    )
    if not hmac.compare_digest(internal_auth, expected):
        raise HTTPException(status_code=401, detail="Authentication required")

    return {
        "project_id": project_id,
        "principal_type": principal_type,
        "principal_id": principal_id,
        "actor_id": actor_id,
    }


def is_public_reader(request: Request) -> bool:
    """True when the request is coming from a trusted wrapper as a public reader.

    Cloud mode uses a signed internal auth context with principal_type="p" to
    allow read-only access for unauthenticated visitors to *public* projects.
    """
    internal = parse_internal_auth_context(request)
    return internal is not None and (internal.get("principal_type") or "") == "p"
