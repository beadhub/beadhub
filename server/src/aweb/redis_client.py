from __future__ import annotations

from fastapi import Request
from redis.asyncio import Redis


def get_redis(request: Request) -> Redis:
    """
    FastAPI dependency that returns the shared async Redis client from app state.
    """
    return request.app.state.redis
