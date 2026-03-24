"""Rate limiting for aweb coordination endpoints.

Provides Redis-based rate limiting with fixed window counters.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import HTTPException, Request
from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

# Rate limit configuration for /v1/workspaces/init endpoint
# Can be overridden via environment for testing
INIT_RATE_LIMIT = int(os.getenv("AWEB_INIT_RATE_LIMIT", "10"))  # requests per window
INIT_RATE_WINDOW = int(os.getenv("AWEB_INIT_RATE_WINDOW", "60"))  # seconds

# Lua script for atomic increment with expiration
# This prevents race condition between INCR and EXPIRE
RATE_LIMIT_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""


def get_client_ip(request: Request) -> str:
    """Extract client IP address from request.

    Uses request.client.host which is set by the ASGI server based on
    the actual TCP connection. This is secure against X-Forwarded-For
    spoofing attacks.

    For deployments behind a reverse proxy, configure the proxy to set
    the client IP correctly, or use FastAPI's TrustedHostMiddleware.
    Do NOT trust X-Forwarded-For without proper proxy configuration.

    Args:
        request: FastAPI request object

    Returns:
        Client IP address string
    """
    # request.client can be None in some test scenarios
    if request.client is None:
        return "unknown"
    return request.client.host


async def check_rate_limit(
    request: Request,
    redis: Redis,
    key_prefix: str,
    limit: int,
    window_seconds: int,
) -> Optional[int]:
    """Check if request is within rate limit.

    Uses a Lua script for atomic increment with expiration. The window
    is fixed from the first request (not sliding).

    Note: Fixed window allows burst at window boundaries (up to 2x limit
    in a short period). This is acceptable for /v1/workspaces/init.

    Args:
        request: FastAPI request object
        redis: Async Redis client
        key_prefix: Prefix for the rate limit key (e.g., "ratelimit:init")
        limit: Maximum requests per window
        window_seconds: Window duration in seconds

    Returns:
        None if within limit, otherwise seconds until limit resets

    Raises:
        RedisError: If Redis is unavailable (caller should handle)
    """
    client_ip = get_client_ip(request)
    key = f"{key_prefix}:{client_ip}"

    # Atomic increment with expiration using Lua script
    # This prevents race condition where INCR succeeds but EXPIRE fails
    current = await redis.eval(RATE_LIMIT_SCRIPT, 1, key, window_seconds)

    if current > limit:
        # Over limit - get TTL for Retry-After header
        ttl = await redis.ttl(key)
        if ttl < 0:
            # Key has no expiry (shouldn't happen with Lua script)
            # Delete and allow retry on next request
            await redis.delete(key)
            ttl = window_seconds
            logger.error(
                "Rate limit key without TTL detected and deleted: ip=%s key=%s",
                client_ip,
                key,
            )
        logger.warning(
            "Rate limit exceeded: ip=%s key=%s count=%d limit=%d",
            client_ip,
            key,
            current,
            limit,
        )
        return ttl

    return None


async def enforce_init_rate_limit(request: Request, redis: Redis) -> None:
    """Enforce rate limit for /v1/workspaces/init endpoint.

    Fails closed: If Redis is unavailable, returns 503 Service Unavailable
    rather than allowing unlimited requests.

    Args:
        request: FastAPI request object
        redis: Async Redis client

    Raises:
        HTTPException: 429 Too Many Requests if rate limit exceeded
        HTTPException: 503 Service Unavailable if Redis is unavailable
    """
    try:
        retry_after = await check_rate_limit(
            request=request,
            redis=redis,
            key_prefix="ratelimit:init",
            limit=INIT_RATE_LIMIT,
            window_seconds=INIT_RATE_WINDOW,
        )
    except RedisError as e:
        # Fail closed: deny request if we can't check rate limit
        logger.error("Redis error during rate limit check: %s", e)
        raise HTTPException(
            status_code=503,
            detail="Service temporarily unavailable. Please retry.",
        )

    if retry_after is not None:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Too many initialization requests.",
            headers={"Retry-After": str(retry_after)},
        )
