import asyncio
from datetime import datetime, timezone

import httpx
import structlog
from sqlalchemy import text

from shared.config import settings
from shared.models import get_session

# Umbrales de inactividad para alertas
_MONITOR_STALE_MIN = 10    # monitor debería ciclar cada 5 min
_DISCOVERY_STALE_H = 26    # discovery corre 1×/día a las 2 AM UTC

log = structlog.get_logger(__name__)

DOCKER_SOCKET = "/var/run/docker.sock"
PROJECT_PREFIX = "crypto_agent_system-"


def _parse_docker_logs(raw: bytes) -> str:
    """Parse Docker multiplexed log stream (8-byte framing header per chunk)."""
    lines = []
    i = 0
    while i + 8 <= len(raw):
        header = raw[i : i + 8]
        size = int.from_bytes(header[4:8], "big")
        i += 8
        if size > 0 and i + size <= len(raw):
            chunk = raw[i : i + size].decode("utf-8", errors="replace").rstrip("\n")
            lines.append(chunk)
        i += size
    return "\n".join(lines)


class HealthChecker:
    async def collect(self) -> dict:
        snapshot: dict = {
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "containers": {},
            "error_logs": {},
            "postgres": {},
            "redis_health": {},
            "agent_activity": {},
        }

        transport = httpx.AsyncHTTPTransport(uds=DOCKER_SOCKET)
        try:
            async with httpx.AsyncClient(
                transport=transport, base_url="http://localhost", timeout=15.0
            ) as client:
                snapshot["containers"] = await self._get_container_statuses(client)

                # Fetch logs in parallel with short timeout — Docker log endpoint
                # hangs on this VPS (same issue as `docker compose logs`)
                running = {
                    svc: info
                    for svc, info in snapshot["containers"].items()
                    if info["state"] == "running"
                }
                log_tasks = {
                    svc: asyncio.create_task(
                        self._get_error_logs(client, info["full_id"])
                    )
                    for svc, info in running.items()
                }
                if log_tasks:
                    results = await asyncio.gather(
                        *log_tasks.values(), return_exceptions=True
                    )
                    for svc, result in zip(log_tasks.keys(), results):
                        if isinstance(result, list) and result:
                            snapshot["error_logs"][svc] = result
        except Exception as e:
            log.warning("health_checker.docker_unavailable", error=str(e))
            snapshot["containers"]["_docker_error"] = str(e)

        snapshot["postgres"] = await self._check_postgres()
        snapshot["redis_health"] = await self._check_redis()
        snapshot["agent_activity"] = await self._check_agent_activity()

        return snapshot

    async def _get_container_statuses(self, client: httpx.AsyncClient) -> dict:
        try:
            r = await client.get("/containers/json", params={"all": "true"})
            r.raise_for_status()
            result = {}
            for c in r.json():
                for raw_name in c.get("Names", []):
                    name = raw_name.lstrip("/")
                    if not name.startswith(PROJECT_PREFIX):
                        continue
                    # crypto_agent_system-monitor-1 → monitor
                    suffix = name[len(PROJECT_PREFIX):]
                    parts = suffix.rsplit("-", 1)
                    service = parts[0] if len(parts) == 2 and parts[1].isdigit() else suffix
                    result[service] = {
                        "full_id": c["Id"],
                        "id": c["Id"][:12],
                        "state": c["State"],
                        "status": c["Status"],
                    }
            return result
        except Exception as e:
            log.warning("health_checker.containers_error", error=str(e))
            return {}

    async def _get_error_logs(
        self, client: httpx.AsyncClient, container_id: str
    ) -> list[str]:
        try:
            r = await client.get(
                f"/containers/{container_id}/logs",
                params={
                    "stdout": "true",
                    "stderr": "true",
                    "follow": "false",
                    "tail": "50",
                    "timestamps": "false",
                },
                timeout=3.0,
            )
            text_content = _parse_docker_logs(r.content)
            errors = [
                line
                for line in text_content.splitlines()
                if any(
                    kw in line.lower()
                    for kw in ("error", "critical", "exception", "traceback", "fatal")
                )
            ]
            return errors[-15:] if errors else []
        except Exception as e:
            log.warning(
                "health_checker.logs_error", container_id=container_id, error=str(e)
            )
            return []

    async def _check_postgres(self) -> dict:
        try:
            async with get_session() as session:
                row = await session.execute(
                    text("SELECT COUNT(*) FROM token_candidates WHERE status='active'")
                )
                active_count = row.scalar()
            return {"ok": True, "active_tokens": active_count}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def _check_redis(self) -> dict:
        import redis.asyncio as aioredis

        try:
            client = aioredis.from_url(settings.redis_url, decode_responses=True)
            await client.ping()
            info = await client.info("memory")
            await client.aclose()
            return {
                "ok": True,
                "used_memory_human": info.get("used_memory_human", "?"),
                "maxmemory_human": info.get("maxmemory_human", "0B"),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def _check_agent_activity(self) -> dict:
        """Detecta agentes inactivos: monitor por DB, scorer/executor por Redis heartbeat."""
        import redis.asyncio as aioredis

        result: dict = {}
        now = datetime.now(timezone.utc)

        # Redis heartbeats — scorer, executor, discovery (todos en una conexión)
        try:
            r = aioredis.from_url(settings.redis_url, decode_responses=True)
            scorer_ttl    = await r.ttl("scorer:heartbeat")
            executor_ttl  = await r.ttl("executor:heartbeat")
            discovery_ttl = await r.ttl("discovery:last_run")
            await r.aclose()
            result["scorer_heartbeat"]   = "ok" if scorer_ttl > 0 else "missing"
            result["executor_heartbeat"] = "ok" if executor_ttl > 0 else "missing"
            if discovery_ttl > 0:
                result["discovery_last_scan_h"] = round((100800 - discovery_ttl) / 3600, 1)
                result["discovery_ok"] = True
            else:
                result["discovery_last_scan_h"] = None
                result["discovery_ok"] = False
        except Exception as e:
            result["heartbeat_error"] = str(e)

        # Actividad del monitor: MAX(last_checked) en token_candidates activos
        try:
            async with get_session() as session:
                row = await session.execute(
                    text("SELECT MAX(last_checked) FROM token_candidates WHERE status='active'")
                )
                last_checked = row.scalar()
            if last_checked:
                if last_checked.tzinfo is None:
                    last_checked = last_checked.replace(tzinfo=timezone.utc)
                monitor_age = round((now - last_checked).total_seconds() / 60, 1)
                result["monitor_last_cycle_min"] = monitor_age
                result["monitor_ok"] = monitor_age <= _MONITOR_STALE_MIN
            else:
                result["monitor_last_cycle_min"] = None
                result["monitor_ok"] = False
        except Exception as e:
            result["monitor_db_error"] = str(e)

        return result
