"""
WebSocketManager: mantiene conexiones activas y hace broadcast de mensajes Redis → WS clients.

Canales:
  "signals" → detector:scored_token  (score >= threshold)
  "trades"  → executor:trade_result  (ejecuciones abiertas/cerradas)
"""
import asyncio
import json
from typing import Callable, Awaitable
import structlog
from fastapi import WebSocket

from shared.redis_bus import bus, Channel

log = structlog.get_logger(__name__)

BroadcastCallback = Callable[[dict], Awaitable[None]]


class WebSocketManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {
            "signals": set(),
            "trades": set(),
        }

    async def connect(self, ws: WebSocket, channel: str) -> None:
        await ws.accept()
        self._connections.setdefault(channel, set()).add(ws)
        log.info("ws_manager.connected", channel=channel, total=self._active_count())

    def disconnect(self, ws: WebSocket, channel: str) -> None:
        self._connections.get(channel, set()).discard(ws)
        log.info("ws_manager.disconnected", channel=channel, total=self._active_count())

    async def broadcast(self, channel: str, payload: dict) -> None:
        connections = list(self._connections.get(channel, set()))
        if not connections:
            return
        dead: list[WebSocket] = []
        for ws in connections:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections[channel].discard(ws)

    def _active_count(self) -> int:
        return sum(len(s) for s in self._connections.values())

    async def start_redis_bridge(self) -> None:
        """
        Suscribe a Redis y hace forward de mensajes a los clientes WS conectados.
        Debe llamarse en un background task del lifespan de FastAPI.
        """
        async def on_signal(payload: dict) -> None:
            await self.broadcast("signals", payload)

        async def on_trade(payload: dict) -> None:
            await self.broadcast("trades", payload)

        await bus.subscribe(Channel.DETECTOR_SCORED_TOKEN, on_signal)
        await bus.subscribe(Channel.EXECUTOR_TRADE_RESULT, on_trade)
        await bus.start_listening()
        log.info("ws_manager.redis_bridge_started")


# Singleton
ws_manager = WebSocketManager()
