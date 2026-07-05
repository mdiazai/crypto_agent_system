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
- SSH: `ssh root@167.88.33.68` — clave `~/.ssh/id_11mkeys` (configurada en `~/.ssh/config`)
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
  - allowed_updates: `message`, `callback_query` (actualizado 2026-06-28)
  - Trigger y respuestas unificados en este bot (cred n8n "11Mkeys PM Bot" id `JGUqhrTxSR2RjdYy`)
  - Credencial duplicada `IyfBxr5585Zirmpv` eliminada 2026-06-13 — queda solo `JGUqhrTxSR2RjdYy`
- **Strategy Advisor:** `@ElevenMkeys_Advisor_bot` (bot_id `8911950382`)
  - Token: `ADVISOR_BOT_TOKEN` en `.env`
  - Webhook: `https://n8n.11mkeys.ai/webhook/6d8966df-6977-4670-a051-b87a08b09fd9/webhook`
- **Monkey Brain:** `@ElevenMkeys_MonkeyBrain_bot` (bot_id `8228343063`)
  - Token: `MONKEY_BRAIN_BOT_TOKEN` en `.env`
  - Webhook: `https://n8n.11mkeys.ai/webhook/c4685dee-8100-4743-90d7-4f53ad819556/webhook`
  - allowed_updates: `message`

## Code Agent Bot — Comandos disponibles
- `/fix_etherscan` — aplica fix Etherscan V2 con aprobación manual
- `/status` — estado contenedores Docker + count holder data
- `/logs` — últimos 20 logs del monitor (lee archivo JSON Docker directo)
- `/scores` — top 10 tokens por `detection_score` desde PostgreSQL
- `approve_deploy` — botón inline para aprobar deploy
- `reject_deploy` — botón inline para rechazar deploy

## PM Agent Bot — Comandos disponibles (actualizado 2026-07-04)
- `/estado` — resumen de tareas activas (conteo por estado)
- `/tareas` — lista de tareas en curso
- `/blockers` — lista de blockers activos
- `/nueva [descripción]` — crea nueva tarea
- `/done [id]` — marca tarea como completada
- `/run [cmd]` — ejecuta comando arbitrario en el VPS (timeout 30s, output truncado a 3800 chars). Comandos bloqueados: `rm -rf`, `docker rm`, `docker rmi`, `git push`, `git reset --hard`
- `/memoria [clave]` — busca registros en `lab_memory` por clave (ej: `/memoria lab_arquitectura_vps`)
- `/memoria proyecto [nombre]` — todo lo de un proyecto (ej: `/memoria proyecto crypto_agent`)
- `/memoria hoy` — registros creados en las últimas 24 horas
- `/ingreso [proyecto] [monto] [descripcion]` — registra ingreso en lab_memory. Proyectos válidos: `crypto_agent`, `estrategia_b`, `depin`, `nodeflow`
- `/finanzas` — dashboard mensual: ingresos reales vs metas por proyecto + % camino a $10K/mes
- **Texto libre técnico** — Claude Classify detecta mensajes técnicos y llama al Task Runner automáticamente
- `tr_approve` (botón inline) — aprueba y deploya el fix pendiente en Redis
- `tr_reject` (botón inline) — rechaza y revierte el archivo a su backup `.tr_bak`
- Fallback: Send Help (para mensajes conversacionales)

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
  - id `HlY3gLWuJowyITB9` — 61 nodos (2026-07-04)
  - Comandos: `/estado`, `/tareas`, `/blockers`, `/nueva`, `/done`, `/run`, `/memoria`, `/ingreso`, `/finanzas`
  - Callbacks: `tr_approve` (deploy), `tr_reject` (revert)
  - Fallback: Claude Classify (Haiku) → TECHNICAL → llama Task Runner | CONVERSATIONAL → Send Help
  - `/ingreso`: Switch[9] → Parse Ingreso → IF Valid → SSH INSERT lab_memory → Fmt OK → Send OK / Send Error
  - `/finanzas`: Switch[10] → Q Finanzas (SSH) → Fmt Finanzas (metas hardcoded) → Send Finanzas
- **Task Runner:** Webhook → SSH context → Claude generate fix → Apply → Diff → Redis → Telegram buttons
  - id `2vlG13sLx4bXAY86` — webhook path: `task-runner`, 16 nodos
  - Redis key `tr:pending` (SETEX 3600) almacena `{file_path, service, rel_path, original_snippet, fixed_snippet, explanation}`
  - Backup automático: `{file}.tr_bak` antes de aplicar fix
- **Weekly Board Agent:** Schedule (domingos 13:00 UTC) → 5x SSH queries → SSH Finance → HTTP Workflows Status → Format Message → Telegram
  - id `rJzmIz9h7XHDymGB` — 10 nodos (2026-07-04) — report semanal: focus checkins, top 5 tokens, containers, alertas, tareas lab, finanzas mes, estado workflows
  - Sección "💰 FINANZAS MES": query ingresos del mes en lab_memory, metas por proyecto
  - Sección "🔧 WORKFLOWS": llama GET /api/v1/workflows, marca ✅ activo o ⚠️ inactivo por workflow
  - Entrega: chat_id 6517856768 via @ElevenMkeys_PM_Bot (cred JGUqhrTxSR2RjdYy)
- **Finance Alerts:** Schedule (lunes 09:00 UTC) → SSH Finance Status → Check Alerts → IF Has Alerts → Send Alert
  - id `0DcLexkKVceomM1z` — 5 nodos, activo (2026-07-04)
  - Alertas: proyecto <50% meta en día 15+, sin ingresos este mes, último ingreso >14 días
  - Entrega via @ElevenMkeys_PM_Bot (cred JGUqhrTxSR2RjdYy)
- **Strategy Advisor:** Telegram Trigger → Parse Input → Route Command → [6 branches] → Claude/SSH/Telegram
  - id `7Ohb4fekhWkgfMVE` — 27 nodos (2026-07-02)
  - Bot: `@ElevenMkeys_Advisor_bot` (cred `OnOkrq5xaWWl9e9j`)
  - Comandos: `/estado`, `/evaluar`, `/proyectos`, `/principios`, `/memoria`, texto libre → Claude Advisor Brain
  - Lee y escribe en `lab_memory` (tipo `estrategica`)
- **Advisor Notify:** Webhook POST `/advisor-notify` → Claude evaluate → Telegram notify Marce → Respond
  - id `mDjJw4IIFJhnZq1j` — 6 nodos
  - Respuesta: `{status: approved/pending_marce, mensaje, id_colaboracion}`
- **Advisor Report:** Webhook POST `/advisor-report` → SSH write lab_memory → Telegram notify → Respond
  - id `mB0dJy17gxM4V3FN` — 5 nodos
  - Escribe tipo `operativa` en lab_memory + notifica a Marce via PM Bot
- **Monkey Brain:** Telegram Trigger → Parse Input → Get MB State (Redis) → Consolidate Data → Route [3 salidas]
  - id `uBR0ICIj2ZtLUCvk` — 49 nodos (2026-07-04)
  - Bot: `@ElevenMkeys_MonkeyBrain_bot` (cred `BPdMxyZ1zYqCfYTx`)
  - [0] New Insight → ack inmediato → Claude genera 3 preguntas dinámicas → Store Redis (TTL 1h)
  - [1] Answers → Parse Redis state → Search lab_memory → Claude Research (web_search tool) → SSH Write insight → Telegram hallazgos → IF project potential → /advisor-notify
  - [2] Commands → /insights, /insight [clave], /conectar [tema], /pendientes, fallback help
  - Schedule 48h → SSH pending insights → Claude investiga → IF conexión significativa → Telegram notifica
  - Redis key `mb:state:{chat_id}` (SETEX 3600) para estado conversacional multi-turno
  - **Nodo Consolidate Data (Code):** fusiona Parse Input + Get MB State antes del Route — necesario porque SSH output solo tiene `{stdout,stderr}` y downstream necesita `chat_id`, `command`, `state`
  - **Parse Research:** concatena TODOS los bloques text de Claude (con web_search la respuesta llega fragmentada en 20-30 bloques) — NO usar solo el último bloque

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
- **Blacklist `/run` agregada 2026-06-24:** `Prep Run` rechaza `rm -rf`, `docker rm`, `docker rmi`, `git push`, `git reset --hard` — devuelve `skip:true` sin llegar al nodo SSH. Probado: exec 221 ✅.
- **Contenedor huérfano eliminado 2026-06-24:** `11mkeys_pm_agent` (`11mkeys-pm-agent:latest`, `python -m agents.pm.pm_agent`) usaba el mismo token `8818804931:…` que el workflow n8n — conflicto de polling vs webhook. Detenido y removido via `/run`. El workflow n8n es la única implementación del PM Agent.

## Infraestructura VPS — Cambios importantes (2026-06-06)
- `WEBHOOK_URL` n8n: `https://n8n.11mkeys.ai/` (permanente en `docker-compose.yml`)
- DNS n8n: `8.8.8.8`, `8.8.4.4` (permanente en `docker-compose.yml`)
- Límites CPU/memoria permanentes en `docker-compose.yml` — 6 servicios (2026-06-08)
- `docker compose logs` se cuelga en este VPS — usar `tail` directo al archivo JSON del contenedor
- `docker compose exec postgres` se cuelga — usar `docker exec` directo con `timeout`

## Comandos seguros para este VPS
- Logs: `docker inspect CONTAINER --format '{{.LogPath}}' | xargs tail -N`
- Status DB: `timeout 10 docker exec crypto_agent_system-postgres-1 psql -U postgres -d crypto_agent -c "QUERY"`
- Status containers: `timeout 8 docker ps | awk 'NR>1 {print "UP " $NF}'`
- **Build de servicios:** `docker build -f /opt/crypto_agent_system/agents/SERVICE/Dockerfile -t crypto_agent_system-SERVICE:latest /opt/crypto_agent_system`
- **Restart:** `docker restart crypto_agent_system-SERVICE-1`
- **NUNCA usar:** `docker compose logs` (se cuelga), `docker compose exec postgres` (se cuelga)
- **NO usar:** `docker compose build` — el `docker-compose.yml` tiene error de validación en v5.1.3 (`deploy.resources` no permitido). Usar `docker build` directo (ver arriba).
- **Git pull en VPS:** `git -C /opt/crypto_agent_system fetch origin master && git -C /opt/crypto_agent_system reset --hard origin/master`

## Focus Guardian — Bot de check-ins (deployado 2026-06-25)
- Container: `focus_guardian` en `crypto_agent_network`
- Bot: `FOCUS_BOT_TOKEN` del `.env` (bot independiente, no PM_BOT_TOKEN)
- Tabla: `focus_checkins` (fecha, tipo, proyecto_declarado, resultado, detalle)
- Scheduler (UTC): check-in mañana 12:00 | timeout sin_respuesta 14:00 | check-in noche 00:00
- Check-in noche: botones inline `fg_avance` / `fg_desvio` + detalle opcional o `/skip`
- Comando `/historial`: últimos 7 registros
- Build context: `/opt/11mkeys_lab` | Dockerfile: `agents/focus/Dockerfile`
- `requirements.txt` creado en repo 11mkeys_lab (asyncpg, apscheduler, anthropic, python-telegram-bot, python-dotenv)

## N8N API Key
- JWT almacenado en `/var/lib/docker/volumes/crypto_agent_system_n8n_data/_data/database.sqlite`
- Extraer con: `strings <path> | grep "^eyJ"`
- Guardada en `/opt/crypto_agent_system/.env` como `N8N_API_KEY` ✅ (2026-06-27)
- Lecciones n8n Telegram node: usar **typeVersion 1.2** + `additionalFields: {}`; typeVersion 1 da 400 Bad Request
- `docker ps --format "{{.Names}}"` rompe n8n (Go templates conflictan con expresiones n8n) — usar `docker ps | awk 'NR>1 {print "UP " $NF}'`
- **Switch v3 — reglas nuevas:** al agregar reglas a un Switch existente via API, usar EXACTAMENTE el mismo `options` de las reglas preexistentes: `{"caseSensitive": true, "leftValue": "", "typeValidation": "strict", "version": 1}`. Options incompleto causa doble routing: el item va al output correcto Y al fallback extra simultáneamente.
- **Parse Input PM Agent:** exporta `{command, args, chat_id}`. `command` = primera palabra en lowercase. `args` = resto del texto. No existe campo `raw`.
- **Parse Input Strategy Advisor:** exporta `{command, args, text, chat_id}`. `text` = mensaje completo. Texto libre → `command = 'text'`.
- **PM Agent SSH nodes post-migración:** `Build Memoria Query`, `Q Estado`, `Q Tareas`, `Q Blockers`, `Insert Task`, `Update Done` migraron de `-d crypto_agent` a `-d lab_11mkeys` el 2026-07-05.
- **APScheduler 3.x + Python 3.11 — async bug:** `AsyncIOScheduler.add_job(async_func)` crea el coroutine pero no lo awaita → `RuntimeWarning: coroutine was never awaited`. Fix: pasar wrapper síncrono que haga `asyncio.get_running_loop().create_task(coro())`. Afecta discovery_agent.py (fix 2026-07-05).

## Task Runner — arquitectura (actualizado 2026-06-29)
- Webhook POST `task: string, chat_id: int` → SSHGetContext (docker ps + DB count) → SSH Get File (si `file_path` en body) → Build Prompt → Build Claude Body (Code JS + JSON.stringify) → Claude Generate Fix (HTTP string body) → Parse Fix → IF Has Fix → SSH Read File → Apply Fix (Code JS replace) → SSH Backup Write → SSH Gen Diff → Build Redis Payload → SSH Store Redis → **Build TG Body (Code)** → **Telegram Send Diff (HTTP Request)**
- Rama false (no fix): Telegram No Fix
- `specifyBody: "string"` en Claude HTTP node (evita error JSON parsing de n8n con heredocs Python)
- IF Has Fix: Switch v3 con `$json.has_fix_str == "yes"` (string comparison, más fiable que boolean)
- **Telegram Send Diff: HTTP Request node v4** (NOT n8n telegram node) → llama directamente `api.telegram.org/bot.../sendMessage` con `reply_markup.inline_keyboard` en el body JSON — typeVersion 1 del nodo Telegram nativo NO envía `reply_markup` correctamente
- Build TG Body: Code node que construye el JSON completo (`chat_id`, `text`, `reply_markup`) y lo pasa como string `tg_body` al HTTP node
- HTTP node params clave: `specifyBody: "string"`, `contentType: "raw"`, `rawContentType: "application/json"`, header `content-type: application/json` explícito — sin estos params el body llega vacío a Telegram

## Finance Agent — metas (B3.1)
- Metas mensuales hardcodeadas: `crypto_agent=$500`, `estrategia_b=$200`, `depin=$120`, `nodeflow=$0` (pre-revenue)
- Total meta: $820/mes → camino a $10K/mes
- Ingresos almacenados en `lab_memory`: tipo=`operativa`, agente=`finance_agent`, clave=`ingreso_{proyecto}_{fecha}_{ts}`, valor=JSON `{proyecto, monto, descripcion, fecha}`
- Query finanzas: `WHERE tipo='operativa' AND agente='finance_agent' AND clave LIKE 'ingreso_%' AND creado_en > date_trunc('month', NOW())`
- B3.2 Soberanía tecnológica: tarea para Monkey Brain (NO Claude Code) — Marce activa manualmente

## Estado del sistema (actualizado 2026-07-04)
- Monitor: 90 tokens activos, 86 publicados, 0 errores por ciclo
- `detection_score` diferenciado ✅ — score máximo 67.5 (EUR) al 2026-06-25
- `holder_concentration_pct` activo vía Moralis ✅
- `agents/monitor/onchain_client.py`: CoinglassClient → **CCXTDerivativesClient** ✅ (MEXC/Bitget perpetuos, cache Redis 5 min)
- `agents/monitor/data_fetcher.py`: `get_funding_rate()` wired al pipeline ✅ — fallback a spot si None
- ZINC/USDT: removido de `token_candidates` (`status='removed'`) ✅
- **chainid fix deployado ✅** (2026-06-27) — `EtherscanClient` y `BscClient` usan `self._CHAIN_ID` en todos los params; commit `b4a14b7`; monitor rebuildeado y corriendo sin errores
- **SmartDevops Agent: operativo y entregando mensajes Telegram ✅** (2026-06-28)
  - Falso positivo "discovery inactivo" eliminado — usa Redis TTL `discovery:last_run` ✅
  - Telegram migrado a MarkdownV2 con `_esc()`/`_esc_code()` — entrega confirmada ✅ (commit `55fb870`)
  - `fix_description` field en respuesta Claude + regla 6b (schema DB) ✅
- **PM Agent: reconstruido y operativo ✅** (2026-06-13)
  - `/run [cmd]` operativo con blacklist: `rm -rf`, `docker rm`, `docker rmi`, `git push`, `git reset --hard`
- **Focus Guardian: deployado y operativo ✅** (2026-06-25)
  - Container `focus_guardian` en `crypto_agent_network`, bot `@ElevenMkeys_Focus_bot`
- **Discovery heartbeat fix: deployado ✅** (2026-07-05) — APScheduler 3.x + Python 3.11 bug; `discovery:last_run` TTL=100795 verificado post-deploy
- **Orchestrator: estable ✅**
- **Claude Code CLI: instalado en VPS** — v2.1.168, auth via `ANTHROPIC_API_KEY` en `~/.bashrc`
- Umbral de alerta (70 pts): no alcanzado — requiere token con volumen > $3M diario
- **Weekly Board Agent: deployado, activo y probado ✅** (2026-06-27) — id `rJzmIz9h7XHDymGB`, 9 nodos, dispara domingos 13:00 UTC
  - Ejecución manual exec 328: `status=success` ✅ — reporte entregado a Telegram
- **Health check semanal workflows: incluido en Weekly Board ✅** — sección WORKFLOWS con detección de inactivos
- **N8N_API_KEY: agregada a /opt/crypto_agent_system/.env ✅** (2026-06-27)
- **Task Runner: deployado y operativo ✅** (2026-06-28) — id `2vlG13sLx4bXAY86`, 17 nodos (Build TG Body + HTTP node)
- **PM Agent Task Runner integration: completa y end-to-end verificada ✅** (2026-06-29)
  - Componente C: callback_query `tr_approve`/`tr_reject` → deploy/revert chain (exec 365/366 success)
  - Componente A: Claude Classify (Haiku) en fallback → TECHNICAL llama Task Runner (exec 367 success)
  - **Telegram Send Diff con botones inline: CONFIRMADO ✅** (exec 399) — HTTP Request node envía `reply_markup` correctamente, botones ✅/❌ llegan a Telegram
  - **Flujo end-to-end completo probado ✅**: texto libre → TECHNICAL → Task Runner → diff + botones → Aprobar → docker build scorer → deploy confirmado
- **lab_memory: tabla creada y operativa ✅** (2026-07-01) — PostgreSQL `lab_11mkeys`, 9 cols, 5 índices, trigger `actualizado_en`
  - 6 registros iniciales: arquitectura VPS, estado agentes, restricciones técnicas, crypto agent, nodeflow, task runner botones
  - Tipos soportados: `operativa`, `estrategica`, `aprendizaje`, `insight`
- **PM Agent /memoria: operativo ✅** (2026-07-01) — 4 nodos nuevos (Build Memoria Query → Q Memoria → Fmt Memoria → Send Memoria)
  - Switch actualizado: 9 reglas, índice 8 → `/memoria`
  - Probado end-to-end: `/memoria lab_arquitectura_vps` devuelve registro correcto (exec 405 ✅)
- **Monkey Brain: deployado y operativo ✅** (2026-07-04) — id `uBR0ICIj2ZtLUCvk`, 49 nodos
  - Flujo multi-turno con Redis state machine (`mb:state:{chat_id}`, SETEX 3600)
  - Claude Research con `web_search_20250305` tool + `anthropic-beta: web-search-2025-03-05`
  - Scheduler 48h para investigación proactiva de insights pendientes
  - Integración Strategy Advisor via `/advisor-notify` cuando detecta potencial de proyecto
  - **End-to-end confirmado ✅** (exec 435): idea → 3 preguntas → respuestas → web search → hallazgos → lab_memory → Advisor notificado
- **Strategy Advisor: deployado y operativo ✅** (2026-07-03)
  - 3 workflows: `7Ohb4fekhWkgfMVE` (Telegram), `mDjJw4IIFJhnZq1j` (notify), `mB0dJy17gxM4V3FN` (report)
  - Bot `@ElevenMkeys_Advisor_bot` (token `ADVISOR_BOT_TOKEN` en .env), cred n8n `OnOkrq5xaWWl9e9j`
  - Webhook: `https://n8n.11mkeys.ai/webhook/6d8966df-6977-4670-a051-b87a08b09fd9/webhook`
  - `/advisor-notify` probado: responde `approved` con Claude + notifica Marce ✅
  - `/advisor-report` probado: escribe en lab_memory + responde JSON ✅
  - `/evaluar`, `/estado`, texto libre: confirmados end-to-end en Telegram ✅ (execs 422-425)
  - **LECCIÓN webhook n8n:** nunca llamar `setWebhook` manualmente en un bot controlado por n8n — n8n registra su propio secret token al activar; override manual causa 403 en todos los mensajes. Fix: desactivar + reactivar workflow.
  - **B4 — Diagnóstico autónomo + escalado Task Runner: deployado ✅** (2026-07-05) — 27 → 32 nodos
    - Flujo texto libre extendido: SSH System State → (context) → Claude clasifica → IF Needs Fix
    - `needs_fix` + confidence high/medium → Telegram Escalate + Build Task Spec + HTTP Task Runner
    - `informational`/`needs_more_info` → Send Advisor directo
    - Claude responde con JSON en primera línea: `{type, confidence, problem_identified, task_spec}`
- **Fixes scoring anti-stablecoin: deployados ✅** (2026-07-04) — commits `97627be` (EUR exclusion), `1301062` (Fix 2+3)
  - Fix 1: `ALERT_THRESHOLD` 55 → 65 en `.env`
  - Fix 2: Executor skips tokens sin `chain`/`contract_address` (no on-chain validation)
  - Fix 3: `price_stability_signal` < 0.3% change → 5 pts (antes 20 pts) — penaliza stablecoins/forex
  - Executor: **reiniciado ✅** — circuit breaker expira automáticamente ~2026-07-05 02:49 UTC
- **B3.1 Finance Agent: deployado y operativo ✅** (2026-07-04)
  - PM Agent: `/ingreso` (Switch[9]) y `/finanzas` (Switch[10]) — 52 → 61 nodos
  - Finance Alerts scheduler: id `0DcLexkKVceomM1z`, lunes 09:00 UTC, activo
  - Weekly Board: SSH Finance + sección 💰 FINANZAS MES — 9 → 10 nodos
  - Datos: JSON en lab_memory, tipo=operativa, agente=finance_agent, clave=ingreso_{proyecto}_{fecha}_{ts}
  - Metas: crypto_agent $500, estrategia_b $200, depin $120, nodeflow $0
  - **End-to-end confirmado ✅** `/ingreso crypto_agent 10 test` → ✅ Ingreso registrado (exec 471)
- **B3.2 Soberanía tecnológica: PENDIENTE** — Marce activa Monkey Brain manualmente (NO Claude Code)
- **B2 Evaluación e integración de proyectos: COMPLETA ✅** (2026-07-04)
  - 4 registros en lab_memory: `b2_evaluacion_crypto_agent`, `b2_evaluacion_estrategia_b`, `b2_evaluacion_depin`, `b2_evaluacion_nodeflow`
  - Crypto Agent: integrado, bloqueante = trades vacíos
  - Estrategia B: integrada, pendiente = criterio retiro trimestral
  - DePIN: requiere decisión ($5k + recursos VPS)
  - NodeFlow: bloqueante = validación con 5 usuarios no iniciada
  - 4 reportes enviados a Telegram via PM Bot
- **Migración DB crypto_agent → lab_11mkeys: COMPLETA ✅** (2026-07-01)
  - `lab_11mkeys` contiene todos los datos (1187 token_candidates, 6 lab_memory, 11 lab_tasks, etc.)
  - `.env` actualizado: `DATABASE_URL` y `POSTGRES_DB` apuntan a `lab_11mkeys`
  - 8 servicios migrados: monitor, scorer, detector, orchestrator, discovery, smartdevops, executor, learner
  - `crypto_agent` DB: mantenida como backup (DROP solo con aprobación explícita, no antes del 2026-07-08)
  - requirements.txt restaurado desde git (commit `c7e3386`) — estaba reemplazado por versión mínima para lab agents
  - Workaround `docker compose up`: `python3` strip deploy blocks → `/tmp/compose_nodeploy.yml` + `--project-directory`

## lab_memory — Memoria centralizada del Lab (2026-07-01)

Tabla en PostgreSQL (`lab_11mkeys`, schema `public`). Memoria compartida entre todos los agentes.

```sql
-- Estructura
CREATE TABLE lab_memory (
  id SERIAL PRIMARY KEY, tipo VARCHAR(20) CHECK (tipo IN ('operativa','estrategica','aprendizaje','insight')),
  agente VARCHAR(50), clave VARCHAR(100), valor TEXT, proyecto VARCHAR(50),
  vigente BOOLEAN DEFAULT true, creado_en TIMESTAMP DEFAULT NOW(), actualizado_en TIMESTAMP DEFAULT NOW()
);
```

**Consultas frecuentes:**
```sql
-- Por clave
SELECT tipo, agente, clave, valor, proyecto, actualizado_en FROM lab_memory WHERE clave ILIKE '%clave%' AND vigente=true;
-- Por proyecto
SELECT tipo, clave, valor FROM lab_memory WHERE proyecto='crypto_agent' AND vigente=true;
-- Hoy
SELECT tipo, clave, LEFT(valor,200), creado_en FROM lab_memory WHERE creado_en > NOW()-INTERVAL '24 hours';
-- Insertar
INSERT INTO lab_memory (tipo, agente, clave, valor, proyecto) VALUES ('aprendizaje','system','clave','valor',null);
```

**Registros (claves):** `lab_arquitectura_vps`, `lab_agentes_estado`, `lab_restricciones_tecnicas`, `proyecto_crypto_agent_estado`, `proyecto_nodeflow_estado`, `task_runner_botones_inline`, `b2_evaluacion_crypto_agent`, `b2_evaluacion_estrategia_b`, `b2_evaluacion_depin`, `b2_evaluacion_nodeflow`

**Acceso vía PM Bot:** `/memoria [clave]` · `/memoria proyecto [nombre]` · `/memoria hoy`

## Migración DB crypto_agent → lab_11mkeys (completada 2026-07-01)
- `lab_11mkeys` es la DB activa — todos los servicios apuntan a ella
- `crypto_agent` sigue existiendo como backup hasta 2026-07-08 (DROP solo con aprobación explícita)
- Workaround compose: `python3` strip `deploy:` blocks → `/tmp/compose_nodeploy.yml`, luego `docker compose -f ... --project-directory /opt/crypto_agent_system up -d --no-build --no-deps [services]`
- requirements.txt: usar `git show c7e3386:requirements.txt` para restaurar si se reemplaza accidentalmente

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