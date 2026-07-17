"""
Dashboard: FastAPI app con JWT, WebSocket, rate limiting y CORS.
Puerto: 8001
"""
import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import sentry_sdk
import structlog
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import make_asgi_app, Counter
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request

from shared.config import settings
from shared.redis_bus import bus
from shared.utils import configure_logging

from .auth import get_current_user
from .websocket_manager import ws_manager
from .routers import auth, tokens, trades, config, agents, performance, narrative

log = structlog.get_logger(__name__)

# ── Rate Limiter ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)

# ── Prometheus ────────────────────────────────────────────────────────────────
WS_CONNECTIONS = Counter("dashboard_ws_connections_total", "Conexiones WebSocket abiertas", ["channel"])
HTTP_REQUESTS = Counter("dashboard_http_requests_total", "Requests HTTP por endpoint", ["method", "path"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa y apaga recursos al arrancar/detener la app."""
    configure_logging()
    if settings.sentry_dsn:
        sentry_sdk.init(dsn=settings.sentry_dsn, traces_sample_rate=0.05)

    await bus.connect()
    bridge_task = asyncio.create_task(ws_manager.start_redis_bridge())
    log.info("dashboard.started", port=8001, paper_trading=settings.paper_trading)

    yield  # la app corre aquí

    bridge_task.cancel()
    try:
        await bridge_task
    except asyncio.CancelledError:
        pass
    await bus.disconnect()
    log.info("dashboard.stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Crypto Agent System — Dashboard",
        description="API de control para el sistema multi-agente de detección de Criminal Pumps.",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # ── Middlewares ───────────────────────────────────────────────────────────
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],   # restringir en producción
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Static files & root UI ────────────────────────────────────────────────
    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", include_in_schema=False)
    async def root():
        return FileResponse(str(static_dir / "index.html"))

    # ── Prometheus metrics endpoint ───────────────────────────────────────────
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(auth.router)
    app.include_router(tokens.router)
    app.include_router(trades.router)
    app.include_router(config.router)
    app.include_router(agents.router)
    app.include_router(performance.router)
    app.include_router(narrative.router)

    # ── Health ────────────────────────────────────────────────────────────────
    @app.get("/health", tags=["system"])
    async def health():
        return {"status": "ok", "paper_trading": settings.paper_trading}

    # ── System health proxy (llama al orchestrator internamente) ──────────────
    @app.get("/system/health", tags=["system"])
    async def system_health(_: dict = Depends(get_current_user)):
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                r = await client.get("http://orchestrator:8080/health")
                return r.json()
        except Exception:
            return {"overall": "unavailable", "agents": []}

    # ── WebSocket: señales en tiempo real ─────────────────────────────────────
    @app.websocket("/ws/signals")
    async def ws_signals(
        websocket: WebSocket,
        token: str = Query(..., description="JWT token"),
    ):
        """Stream en tiempo real de tokens con score >= ALERT_THRESHOLD."""
        try:
            await get_current_user(token)
        except Exception:
            await websocket.close(code=1008)
            return

        await ws_manager.connect(websocket, "signals")
        WS_CONNECTIONS.labels(channel="signals").inc()
        try:
            while True:
                # Mantener conexión viva con ping cada 30s
                await asyncio.sleep(30)
                await websocket.send_json({"type": "ping"})
        except WebSocketDisconnect:
            ws_manager.disconnect(websocket, "signals")

    # ── WebSocket: trades en tiempo real ──────────────────────────────────────
    @app.websocket("/ws/trades")
    async def ws_trades(
        websocket: WebSocket,
        token: str = Query(..., description="JWT token"),
    ):
        """Stream en tiempo real de ejecuciones de trades."""
        try:
            await get_current_user(token)
        except Exception:
            await websocket.close(code=1008)
            return

        await ws_manager.connect(websocket, "trades")
        WS_CONNECTIONS.labels(channel="trades").inc()
        try:
            while True:
                await asyncio.sleep(30)
                await websocket.send_json({"type": "ping"})
        except WebSocketDisconnect:
            ws_manager.disconnect(websocket, "trades")

    return app


app = create_app()
