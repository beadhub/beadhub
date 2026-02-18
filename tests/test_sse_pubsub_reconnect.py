import asyncio

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from beadhub.events import stream_events_multi


class _FakePubSub:
    def __init__(self, *, fail_first_get: bool):
        self._fail_first_get = fail_first_get
        self._get_calls = 0

    async def subscribe(self, *channels: str) -> None:
        return None

    async def get_message(self, *, ignore_subscribe_messages: bool, timeout: float) -> None:
        self._get_calls += 1
        await asyncio.sleep(0.02)
        if self._fail_first_get and self._get_calls == 1:
            raise RedisConnectionError("Connection closed by server.")
        return None

    async def ping(self) -> None:
        return None

    async def unsubscribe(self, *channels: str) -> None:
        return None

    async def aclose(self) -> None:
        return None


class _FakeRedis:
    def __init__(self) -> None:
        self.pubsub_calls = 0

    def pubsub(self) -> _FakePubSub:
        self.pubsub_calls += 1
        return _FakePubSub(fail_first_get=self.pubsub_calls == 1)


@pytest.mark.asyncio
async def test_stream_events_multi_reconnects_after_pubsub_disconnect():
    redis = _FakeRedis()

    async def check_disconnected() -> bool:
        return False

    gen = stream_events_multi(
        redis,
        ["ws-1"],
        keepalive_seconds=0.01,
        check_disconnected=check_disconnected,
    )

    frames: list[str] = []
    try:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 1.0
        while loop.time() < deadline and redis.pubsub_calls < 2:
            frames.append(await asyncio.wait_for(gen.__anext__(), timeout=1.0))
    finally:
        await gen.aclose()

    assert any(f.startswith(": keepalive") for f in frames)
    assert redis.pubsub_calls >= 2
