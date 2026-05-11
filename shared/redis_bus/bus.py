import asyncio
import json
from typing import Any, Callable, Awaitable
import structlog

import redis.asyncio as aioredis

from shared.config import settings

log = structlog.get_logger(__name__)


class RedisMessageBus:
    def __init__(self) -> None:
        self._client: aioredis.Redis | None = None
        self._pubsub: aioredis.client.PubSub | None = None
        self._subscriptions: dict[str, list[Callable[[dict], Awaitable[None]]]] = {}
        self._listener_task: asyncio.Task | None = None

    async def connect(self) -> None:
        self._client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        await self._client.ping()
        log.info("redis_bus.connected", url=settings.redis_url)

    async def disconnect(self) -> None:
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        if self._pubsub:
            await self._pubsub.close()
        if self._client:
            await self._client.aclose()
        log.info("redis_bus.disconnected")

    async def publish(self, channel: str, payload: dict[str, Any]) -> None:
        if not self._client:
            raise RuntimeError("RedisMessageBus not connected. Call connect() first.")
        message = json.dumps(payload, default=str)
        await self._client.publish(channel, message)
        log.debug("redis_bus.published", channel=channel, payload_keys=list(payload.keys()))

    async def subscribe(
        self,
        channel: str,
        callback: Callable[[dict], Awaitable[None]],
    ) -> None:
        if channel not in self._subscriptions:
            self._subscriptions[channel] = []
        self._subscriptions[channel].append(callback)
        log.info("redis_bus.subscribed", channel=channel)

    async def start_listening(self) -> None:
        if not self._client:
            raise RuntimeError("RedisMessageBus not connected.")
        self._pubsub = self._client.pubsub()
        channels = list(self._subscriptions.keys())
        if channels:
            await self._pubsub.subscribe(*channels)
        self._listener_task = asyncio.create_task(self._listen_loop())
        log.info("redis_bus.listener_started", channels=channels)

    async def _listen_loop(self) -> None:
        if not self._pubsub:
            return
        async for message in self._pubsub.listen():
            if message["type"] != "message":
                continue
            channel: str = message["channel"]
            try:
                payload: dict = json.loads(message["data"])
            except json.JSONDecodeError:
                log.warning("redis_bus.invalid_json", channel=channel)
                continue

            handlers = self._subscriptions.get(channel, [])
            for handler in handlers:
                try:
                    await handler(payload)
                except Exception:
                    log.exception("redis_bus.handler_error", channel=channel)


# Singleton
bus = RedisMessageBus()
