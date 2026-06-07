import asyncio
from datetime import datetime, timezone

import httpx
import structlog
from sqlalchemy import text

from shared.config import settings
from shared.models import get_session

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
        }

        transport = httpx.AsyncHTTPTransport(uds=DOCKER_SOCKET)
        try:
            async with httpx.AsyncClient(
                transport=transport, base_url="http://localhost", timeout=15.0
            ) as client:
                snapshot["containers"] = await self._get_container_statuses(client)
                for service, info in snapshot["containers"].items():
                    if info["state"] == "running":
                        errors = await self._get_error_logs(client, info["full_id"])
                        if errors:
                            snapshot["error_logs"][service] = errors
        except Exception as e:
            log.warning("health_checker.docker_unavailable", error=str(e))
            snapshot["containers"]["_docker_error"] = str(e)

        snapshot["postgres"] = await self._check_postgres()
        snapshot["redis_health"] = await self._check_redis()

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
                    "tail": "50",
                    "timestamps": "false",
                },
                timeout=10.0,
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
