import json

import httpx
import structlog
from sqlalchemy import text

from shared.config import settings
from shared.models import get_session

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

5b. dashboard: es un servidor web pasivo — NO tiene ni tendrá heartbeat propio,
   nunca lo evalúes por ausencia de heartbeat. Su salud se determina EXCLUSIVAMENTE
   por el resultado del HTTP check (sección DASHBOARD del snapshot):
   → dashboard.ok=true (200) → no es un problema, no lo menciones como inactividad
   → dashboard.ok=false (sin respuesta / error / status≠200):
     severity=warn, fix_command: docker restart crypto_agent_system-dashboard-1

6. Logs con ERROR/CRITICAL/Exception repetidos (> 5 en últimas 50 líneas = problema real):
   → severity=warn, fix_command: docker restart del servicio afectado

6b. Error de esquema de base de datos (UndefinedColumnError, UndefinedTableError, column does not exist):
   → severity=warn, NO proponer docker restart (no resuelve problemas de esquema)
   → fix_command: timeout 10 docker exec crypto_agent_system-postgres-1 psql -U postgres -d crypto_agent -c 'SELECT column_name FROM information_schema.columns WHERE table_name=TABLE'
   → diagnosis debe explicar exactamente qué columna falta y en qué tabla, y sugerir revisar el código que genera la query

7. PostgreSQL inaccesible o 0 tokens activos:
   → severity=critical, fix_command: docker restart crypto_agent_system-postgres-1

8. Todo normal → severity=ok, fix_command=null

IMPORTANTE: si detectás un problema de inactividad de agente, siempre proponé
`docker restart crypto_agent_system-SERVICE-1` como fix_command — NO digas
"verificá los contenedores" ni dejes fix_command=null cuando hay una acción clara.

Si el snapshot incluye una sección APRENDIZAJES LAB MEMORY, usala para evitar
repetir diagnósticos incorrectos documentados previamente (tipo 'aprendizaje').

Respondé SIEMPRE con JSON válido y nada más:
{"severity":"ok|warn|critical","diagnosis":"descripción concisa en español","fix_command":"comando bash único o null","fix_description":"descripción en español ≤80 chars de qué hace el fix, o null"}
""".strip()


class ClaudeDiagnostics:
    async def diagnose(self, snapshot: dict) -> dict:
        rag_ctx = await self._get_rag_context()
        prompt = self._build_prompt(snapshot, rag_ctx)
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
                "fix_description": None,
            }

    async def _get_rag_context(self) -> str:
        """Query lab_memory for relevant context before diagnosing."""
        try:
            async with get_session() as session:
                q = text(
                    "SELECT tipo || ': ' || clave || ' -- ' || "
                    "LEFT(REPLACE(REPLACE(valor, chr(10), ' '), chr(13), ''), 300) "
                    "FROM lab_memory "
                    "WHERE vigente = true "
                    "AND (tipo = 'aprendizaje' "
                    "OR (agente = 'smartdevops' AND creado_en > NOW() - INTERVAL '7 days') "
                    "OR (tipo = 'estrategica' AND proyecto = 'crypto_agent')) "
                    "ORDER BY tipo, creado_en DESC LIMIT 8"
                )
                result = await session.execute(q)
                rows = result.fetchall()
                if rows:
                    return "\n".join(r[0] for r in rows)
        except Exception as e:
            log.warning("claude_diagnostics.rag_error", error=str(e))
        return ""

    def _build_prompt(self, snapshot: dict, rag_ctx: str = "") -> str:
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

        lines.append("\n=== DASHBOARD (HTTP check, sin heartbeat) ===")
        dash = snapshot.get("dashboard", {})
        if dash.get("ok"):
            lines.append(f"  OK — HTTP {dash.get('status_code')}")
        else:
            detail = dash.get("error") or f"HTTP {dash.get('status_code', '?')}"
            lines.append(f"  ERROR: {detail} ⚠️")

        if rag_ctx:
            lines.append("\n=== APRENDIZAJES LAB MEMORY ===")
            lines.append(rag_ctx)

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
                "fix_description": data.get("fix_description") or None,
            }
        except json.JSONDecodeError:
            return {"severity": "warn", "diagnosis": text, "fix_command": None}
