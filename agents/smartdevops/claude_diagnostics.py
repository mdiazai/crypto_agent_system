import json

import httpx
import structlog

from shared.config import settings

log = structlog.get_logger(__name__)

_SYSTEM_PROMPT = """
Sos el SmartDevops AI del sistema crypto_agent_system en producción (VPS 167.88.33.68).
Tu rol: analizar snapshots de salud del sistema y detectar problemas reales.

REGLAS CRÍTICAS — comandos prohibidos que CUELGAN el VPS:
- NUNCA: docker compose logs
- NUNCA: docker compose exec postgres
- NUNCA: docker compose exec redis

Comandos SEGUROS para el fix_command:
- docker restart crypto_agent_system-SERVICE-1
- docker start crypto_agent_system-SERVICE-1
- docker logs crypto_agent_system-SERVICE-1 --tail 30 --no-color 2>&1
- timeout 10 docker exec crypto_agent_system-postgres-1 psql -U postgres -d crypto_agent -c "QUERY"
- timeout 5 docker exec crypto_agent_system-redis-1 redis-cli COMMAND

Servicios: orchestrator, discovery, monitor, detector, scorer, executor, learner, dashboard, postgres, redis.

REGLAS DE DIAGNÓSTICO — aplicar en orden:

1. Contenedor caído o reiniciando:
   → severity=critical, fix_command: docker restart crypto_agent_system-SERVICE-1

2. monitor_last_cycle_min > 10 (monitor sin ciclar):
   → severity=warn, fix_command: docker restart crypto_agent_system-monitor-1

3. discovery_last_scan_h > 26 (discovery sin correr en más de 1 día):
   → severity=warn, fix_command: docker restart crypto_agent_system-discovery-1

4. scorer_heartbeat=missing (scorer sin responder):
   → severity=warn, fix_command: docker restart crypto_agent_system-scorer-1

5. executor_heartbeat=missing (executor sin responder):
   → severity=warn, fix_command: docker restart crypto_agent_system-executor-1

6. Logs con ERROR/CRITICAL/Exception repetidos (> 5 en últimas 50 líneas = problema real):
   → severity=warn, fix_command: docker restart del servicio afectado

7. PostgreSQL inaccesible o 0 tokens activos:
   → severity=critical, fix_command: docker restart crypto_agent_system-postgres-1

8. Todo normal → severity=ok, fix_command=null

IMPORTANTE: si detectás un problema de inactividad de agente, siempre proponé
`docker restart crypto_agent_system-SERVICE-1` como fix_command — NO digas
"verificá los contenedores" ni dejes fix_command=null cuando hay una acción clara.

Respondé SIEMPRE con JSON válido y nada más:
{"severity":"ok|warn|critical","diagnosis":"descripción concisa en español","fix_command":"comando bash único o null"}
""".strip()


class ClaudeDiagnostics:
    async def diagnose(self, snapshot: dict) -> dict:
        prompt = self._build_prompt(snapshot)
        try:
            response = await self._call_claude(prompt)
            result = self._parse_response(response)
            log.info(
                "claude_diagnostics.result",
                severity=result["severity"],
                has_fix=result["fix_command"] is not None,
            )
            return result
        except Exception as e:
            log.error("claude_diagnostics.error", error=str(e))
            return {
                "severity": "warn",
                "diagnosis": f"No se pudo obtener diagnóstico de Claude: {e}",
                "fix_command": None,
            }

    def _build_prompt(self, snapshot: dict) -> str:
        lines = [f"Timestamp: {snapshot.get('collected_at', '?')}"]

        lines.append("\n=== CONTENEDORES ===")
        containers = snapshot.get("containers", {})
        if not containers:
            lines.append("No se pudo obtener información de contenedores.")
        for service, info in containers.items():
            if service == "_docker_error":
                lines.append(f"ERROR accediendo a Docker: {info}")
                continue
            state = info.get("state", "?")
            status = info.get("status", "?")
            flag = " ⚠️" if state != "running" else ""
            lines.append(f"  {service}: {state} | {status}{flag}")

        lines.append("\n=== LOGS CON ERRORES ===")
        error_logs = snapshot.get("error_logs", {})
        if not error_logs:
            lines.append("Sin errores detectados en logs.")
        for service, errors in error_logs.items():
            lines.append(f"  [{service}] {len(errors)} errores:")
            for err in errors[:5]:
                lines.append(f"    {err[:200]}")

        lines.append("\n=== POSTGRESQL ===")
        pg = snapshot.get("postgres", {})
        if pg.get("ok"):
            lines.append(f"  OK — tokens activos: {pg.get('active_tokens', '?')}")
        else:
            lines.append(f"  ERROR: {pg.get('error', '?')}")

        lines.append("\n=== REDIS ===")
        redis = snapshot.get("redis_health", {})
        if redis.get("ok"):
            lines.append(
                f"  OK — memoria: {redis.get('used_memory_human', '?')} / {redis.get('maxmemory_human', '?')}"
            )
        else:
            lines.append(f"  ERROR: {redis.get('error', '?')}")

        lines.append("\n=== ACTIVIDAD DE AGENTES ===")
        act = snapshot.get("agent_activity", {})
        if act.get("heartbeat_error"):
            lines.append(f"  ERROR leyendo heartbeats: {act['heartbeat_error']}")
        else:
            scorer_hb = act.get("scorer_heartbeat", "unknown")
            executor_hb = act.get("executor_heartbeat", "unknown")
            lines.append(f"  scorer.heartbeat:   {scorer_hb}{' ⚠️' if scorer_hb == 'missing' else ''}")
            lines.append(f"  executor.heartbeat: {executor_hb}{' ⚠️' if executor_hb == 'missing' else ''}")

        mon_min = act.get("monitor_last_cycle_min")
        if mon_min is not None:
            flag = " ⚠️ INACTIVO" if not act.get("monitor_ok", True) else ""
            lines.append(f"  monitor.last_cycle: {mon_min} min ago{flag}")
        elif act.get("monitor_db_error"):
            lines.append(f"  monitor.last_cycle: ERROR — {act['monitor_db_error']}")
        else:
            lines.append("  monitor.last_cycle: sin datos")

        disc_h = act.get("discovery_last_scan_h")
        if disc_h is not None:
            flag = " ⚠️ INACTIVO" if not act.get("discovery_ok", True) else ""
            lines.append(f"  discovery.last_scan: {disc_h} h ago{flag}")
        elif act.get("discovery_db_error"):
            lines.append(f"  discovery.last_scan: ERROR — {act['discovery_db_error']}")
        else:
            lines.append("  discovery.last_scan: sin datos")

        return "\n".join(lines)

    async def _call_claude(self, user_message: str) -> str:
        headers = {
            "x-api-key": settings.anthropic_api_key.get_secret_value(),
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        body = {
            "model": settings.claude_model,
            "max_tokens": 512,
            "system": _SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_message}],
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=body,
            )
            r.raise_for_status()
            return r.json()["content"][0]["text"]

    def _parse_response(self, text: str) -> dict:
        text = text.strip()
        # Strip markdown fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        try:
            data = json.loads(text)
            return {
                "severity": data.get("severity", "warn"),
                "diagnosis": data.get("diagnosis", text),
                "fix_command": data.get("fix_command") or None,
            }
        except json.JSONDecodeError:
            return {"severity": "warn", "diagnosis": text, "fix_command": None}
