# CLAUDE.md — 11mkeys_lab

## Descripción
Stack de automatización del 11Mkeys IA Lab.
Orquesta el Crypto Agent System y futuros proyectos del lab
mediante n8n, bots de Telegram y la Claude API.

## Objetivo inmediato
Implementar Code Agent + Monkey Advisor sobre el VPS
donde ya corre el Crypto Agent System.

## VPS
- IP: 167.88.33.68
- SSH: ssh root@167.88.33.68
- Proyecto crypto: /opt/crypto_agent_system
- Proyecto lab: /opt/11mkeys_lab (a crear)

## Stack
n8n · Claude API · Telegram bots · bash scripts

## Documento de referencia
Ver: 11MKEYS_CODE_AGENT_SETUP_v2.md — contiene el plan
completo de 5 pasos con los workflows JSON listos para importar.

## Estado
- [x] PASO 0 — Crear bots de Telegram
- [x] PASO 1 — Agregar n8n al docker-compose.yml del crypto system
- [x] PASO 2 — Importar workflow Code Agent en n8n
- [x] PASO 3 — Importar workflow Monkey Advisor en n8n
- [x] PASO 4 — Configurar credenciales en n8n
- [x] PASO 5 — Registrar webhooks y probar

## Infraestructura n8n
- n8n corre en Docker en VPS Hostinger
- IP VPS: 167.88.33.68 — SSH: `ssh root@167.88.33.68`
- n8n path: `/opt/crypto_agent_system` (docker-compose + override)
- Dominio permanente: https://n8n.11mkeys.ai
- SSL: Let's Encrypt, vence 2026-08-30, renovación automática
- Nginx como reverse proxy a localhost:5678
- Puertos 80 y 443 abiertos en UFW

## Bots Telegram
- **Monkey Advisor:** `@MonkeyAdvisor_11Mkeys_bot`
  - Token: `8829243525:AAGvN7WJsGbM3Hfg0uDAPUog38yALBOghdQ`
  - Webhook: `https://n8n.11mkeys.ai/webhook/4ddb16b8-171d-4811-8da5-65e99b4ee153/webhook`
- **Code Agent:** `@ElevenMkeys_CodeAgent_bot`
  - Token: `8763657547:AAHBZoVejJnmYbg2n0gmOqQ48nLmqPjfvqM`
  - Webhook: `https://n8n.11mkeys.ai/webhook/c1a5e861-f106-4d7d-82e2-0be00cc13a7c/webhook`
  - allowed_updates: `message`, `callback_query`
- **SmartDevops Agent:** `@ElevenMkeys_SmartDevops_bot`
  - Token: `8141614556:AAEbY07qhTW0idh5BaH5fMjv2JPt2PY1mV0`
  - Webhook: `https://n8n.11mkeys.ai/webhook/4e2d5c25-11ce-476c-85c7-d45f847f168c/webhook`
  - allowed_updates: `callback_query`
- **PM Agent:** `@ElevenMkeys_PM_Bot` (bot_id `8818804931`)
  - Token: `8818804931:AAGYdiaWTx-rr_M0sMxRUJzN9Gy05bbH9Fc`
  - Webhook: `https://n8n.11mkeys.ai/webhook/20246b71-c0a8-4af5-a406-e93749e29524/webhook`
  - allowed_updates: `message`
  - Trigger y respuestas unificados en este bot (cred n8n "11Mkeys PM Bot" id `JGUqhrTxSR2RjdYy`)
  - Credencial duplicada `IyfBxr5585Zirmpv` eliminada 2026-06-13 — queda solo `JGUqhrTxSR2RjdYy`

## Code Agent Bot — Comandos disponibles
- `/fix_etherscan` — aplica fix Etherscan V2 con aprobación manual
- `/status` — estado contenedores Docker + count holder data
- `/logs` — últimos 20 logs del monitor (lee archivo JSON Docker directo)
- `/scores` — top 10 tokens por `detection_score` desde PostgreSQL
- `approve_deploy` — botón inline para aprobar deploy
- `reject_deploy` — botón inline para rechazar deploy

## PM Agent Bot — Comandos disponibles (actualizado 2026-06-24)
- `/estado` — resumen de tareas activas (conteo por estado)
- `/tareas` — lista de tareas en curso
- `/blockers` — lista de blockers activos
- `/nueva [descripción]` — crea nueva tarea
- `/done [id]` — marca tarea como completada
- `/run [cmd]` — ejecuta comando arbitrario en el VPS (timeout 30s, output truncado a 3800 chars)
- Fallback: Send Help (para comandos no reconocidos)

Bot unificado: trigger y respuestas por el mismo bot `@ElevenMkeys_PM_Bot` (ver bitácora 2026-06-13).

## SmartDevops Agent — Arquitectura
- Ciclo cada 30 min: Docker API + PostgreSQL + Redis → Claude diagnóstico → Telegram propuesta
- Bot `@ElevenMkeys_SmartDevops_bot` envía mensaje con botones `sd_approve` / `sd_ignore`
- n8n workflow `11Mkeys SmartDevops Agent` ejecuta el comando vía SSH al aprobar
- Redis key `smartdevops:pending_command` (SETEX 3600) como IPC entre Python y n8n
- Historial en tabla `diagnostics_log` (PostgreSQL)
- Docker socket montado: `/var/run/docker.sock` (usa Docker API, no binario)
- Logs de contenedores via Docker API en paralelo con timeout 3s por contenedor

## Arquitectura n8n Code Agent (v7)
- Route Command → 3 outputs: `fix_etherscan`, `approve_deploy`, `reject_deploy`
- Ops Router → 3 outputs: `/status`, `/logs`, `/scores`

## Workflows n8n
- **Monkey Advisor:** Telegram Trigger → Get System Context → Anthropic (nativo) → Send a text message
- **Code Agent:** Telegram Trigger → Route Command → Ops Router (arquitectura dual switch)
- **SmartDevops Agent:** Telegram Trigger (callback_query) → Route Command → SSH execute/ignore → Telegram notify
- **PM Agent:** Telegram Trigger → Parse Input → Route Command → nodos SSH (queries psql) → Fmt → Telegram
  - id `HlY3gLWuJowyITB9` — comandos `/estado`, `/tareas`, `/blockers`, nueva tarea, marcar done

## PM Agent — nodos SSH (2026-06-13)
- El nodo `n8n-nodes-base.executeCommand` **no existe** en esta versión de n8n → migrado a `n8n-nodes-base.ssh`
- Nodo SSH instalado es **v1**: usar `resource: "command"`, `operation: "execute"` (NO `executeCommand`)
- Credencial SSH: tipo **`sshPassword`**, nombre "VPS SSH", id `jDAII1GLoOwffiad` (NO `sshApi`)
- 5 nodos convertidos: `Q Estado`, `Q Tareas`, `Q Blockers`, `Insert Task`, `Update Done`
- Import: `PUT /api/v1/workflows/{id}` con body `name/nodes/connections/settings`; `settings` solo `{"executionOrder":"v1"}` (API rechaza `binaryMode`)
- **Workflow estaba a medio cablear (preexistente):** `Route Command` (Switch v3) sin reglas/conexiones; 5 nodos SSH huérfanos. Cableado reconstruido 2026-06-13.
- Switch v3: 5 reglas por `{{ $json.command }}` (`/estado`,`/tareas`,`/blockers`,`/nueva`,`/done`) + `options.fallbackOutput:"extra"` → `Send Help`
- `Send Nueva OK`/`Send Nueva Error` no tenían credencial Telegram → asignada "11Mkeys PM Bot" (id `JGUqhrTxSR2RjdYy`)
- **Activo ✅ y probado end-to-end** (execId 99): `Q Estado` SSH devuelve `2|3|0|0`, formato OK; `Send Estado` solo falla con chat de prueba ficticio ("chat not found")
- Prueba simulada: `POST` al webhook con header `X-Telegram-Bot-Api-Secret-Token` = `${workflowId}_${nodeId}` (chars no válidos eliminados)
- **Bot unificado (2026-06-13):** trigger Y respuestas ahora en `@ElevenMkeys_PM_Bot` (antes el trigger escuchaba en el bot SmartDevops y rompía su webhook). El SmartDevops bot quedó liberado y su webhook restaurado.
- Pendiente: prueba real enviando `/estado` a `@ElevenMkeys_PM_Bot` (iniciar el bot con /start primero)
- **`/run [cmd]` agregado 2026-06-24:** 6 nodos nuevos (Prep Run → IF Run Valid → SSH Run / Send Run Error → Fmt Run → Send Run). Switch v3 ahora tiene 6 reglas + fallback. Actualizado via PUT API con nueva key (todos los scopes). La key anterior solo tenía workflow:read + workflow:update y no podía acceder a endpoints individuales.
- **Contenedor huérfano eliminado 2026-06-24:** `11mkeys_pm_agent` (`11mkeys-pm-agent:latest`, `python -m agents.pm.pm_agent`) usaba el mismo token `8818804931:…` que el workflow n8n — conflicto de polling vs webhook. Detenido y removido via `/run`. El workflow n8n es la única implementación del PM Agent.

## Infraestructura VPS — Cambios importantes (2026-06-06)
- `WEBHOOK_URL` n8n: `https://n8n.11mkeys.ai/` (permanente en `docker-compose.yml`)
- DNS n8n: `8.8.8.8`, `8.8.4.4` (permanente en `docker-compose.yml`)
- Límites CPU/memoria permanentes en `docker-compose.yml` — 6 servicios (2026-06-08)
- `docker compose logs` se cuelga en este VPS — usar `tail` directo al archivo JSON del contenedor
- `docker compose exec postgres` se cuelga — usar `docker exec` directo con `timeout`

## Comandos seguros para este VPS
- Logs: `tail -N /var/lib/docker/containers/CONTAINER_ID/*-json.log`
- LogPath (obtener ruta real): `docker inspect CONTAINER --format "{{.LogPath}}"`
- Status DB: `timeout 10 docker exec crypto_agent_system-postgres-1 psql -U postgres -d crypto_agent -c "QUERY"`
- Status containers: `timeout 8 docker ps --format ...`
- **NUNCA usar:** `docker compose logs` (se cuelga), `docker compose exec postgres` (se cuelga)

## Estado del sistema (actualizado 2026-06-21)
- Monitor: 84 tokens activos, 83 publicados, 0 errores por ciclo
- `detection_score` diferenciado ✅ — score máximo 41.87 (GUA), subió de 34.73 post-fix funding
- `holder_concentration_pct` activo vía Moralis ✅
- `agents/monitor/onchain_client.py`: CoinglassClient → **CCXTDerivativesClient** ✅ (MEXC/Bitget perpetuos, cache Redis 5 min)
- `agents/monitor/data_fetcher.py`: `get_funding_rate()` wired al pipeline ✅ — fallback a spot si None
- ZINC/USDT: removido de `token_candidates` (`status='removed'`) ✅
- **SmartDevops Agent: deployado y operativo ✅**
- **PM Agent: reconstruido y operativo ✅** (2026-06-13)
- **Orchestrator: estable ✅**
- **Claude Code CLI: instalado en VPS** — v2.1.168, auth via `ANTHROPIC_API_KEY` en `~/.bashrc`
- Umbral de alerta (70 pts): no alcanzado — requiere token con volumen > $3M diario
- **Pendiente — chainid fix:** revisar fix de Code Agent que hardcodea `chainid:1` en `EtherscanClient` y `BscClient`; incorrecto para BSC (requiere `chainid:56`) — el fix correcto verifica `self._CHAIN_ID` en `__init__` de cada clase
- **Pendiente — health check semanal:** establecer health check de domingos para workflow "Code Agent v5-fix-chatid"

## Fix scorer aplanado (2026-06-07)
- **Root cause**: `inflow_threshold_usd=500k` calibrado para large-caps; `inflow_1h_usd=None` hardcodeado; CryptoQuant solo cubre BTC/ETH/etc.
- **Fix 1**: `inflow_threshold_usd` 500k → 100k en `shared/config/settings.py`
- **Fix 2**: `inflow_1h_usd = volume_usd / 24` (proxy horario) en `agents/monitor/data_fetcher.py`
- **Resultado**: scores diferenciados, máximo 41.87 pts post-fix funding pipeline

## CPU/memoria limits (docker-compose.yml) — 2026-06-08
| Servicio | CPUs | Memoria |
|---|---|---|
| monitor | 0.50 | 512m |
| detector | 0.30 | 256m |
| scorer | 0.30 | 256m |
| orchestrator | 0.30 | 256m |
| smartdevops | 0.50 | 256m |
| n8n | 1.00 | 1g |

## Protocolo obligatorio — Code Agent (actualizado 2026-06-20)

1. **Diagnóstico antes de acción** — usar solo comandos de lectura (`cat`, `head`, `tail`, `docker inspect`, `git log`, `docker ps`) y reportar output completo antes de proponer fix.
2. **Diff obligatorio antes de sobrescribir** — nunca sobreescribir un archivo sin mostrar el diff completo y esperar aprobación explícita.
3. **Sin commits ni push sin aprobación** — nunca ejecutar `git commit` ni `git push` sin aprobación explícita.
4. **Deploy de un servicio a la vez** — nunca deployar más de un servicio simultáneamente sin aprobación.
5. **Mensajes conversacionales en texto plano** — solo `/fix [descripción]` activa el flujo completo; mensajes de consulta no invocan herramientas de modificación.
6. **No reportar "completado" con errores activos** — nunca reportar "completado" si el servicio sigue en estado de error.

### Restricciones técnicas VPS (reafirmadas)

- **NUNCA usar:** `docker compose logs` (se cuelga), `docker compose exec postgres` (se cuelga)
- **Logs:** `docker inspect CONTAINER --format "{{.LogPath}}"` → `tail -N <path>`
- **DB:** `timeout 10 docker exec crypto_agent_system-postgres-1 psql -U postgres -d crypto_agent -c "QUERY"`
- **Deploy seguro:** `docker compose build SERVICE && docker compose up -d --no-deps SERVICE`

### Proyectos en el VPS

- `/opt/crypto_agent_system` — Crypto Agent System
- `/opt/11mkeys_lab` — Lab projects

## Reglas
- Nunca modificar /opt/crypto_agent_system directamente
  salvo los cambios específicos del PASO 1 (agregar n8n al compose)
- Cada paso requiere confirmación antes de continuar
- Actualizar este archivo al finalizar cada sesión