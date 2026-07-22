# CLAUDE.md — 11mkeys_lab
## Actualizado: 2026-07-21

## Descripción
Stack de automatización del 11Mkeys AI Lab.
Sistema multi-agente con memoria RAG compartida (lab_memory),
orquestado via n8n, bots de Telegram y Claude API.
Estadio 2 operativo desde 2026-07-04: agentes coordinados via Strategy Advisor.

## VPS
- IP: 167.88.33.68
- SSH: `ssh root@167.88.33.68` — clave `~/.ssh/id_11mkeys`
- Proyecto crypto: /opt/crypto_agent_system
- Proyecto lab: /opt/11mkeys_lab

## Base de datos
- DB principal: lab_11mkeys (migrada desde crypto_agent el 2026-07-01)
- DB legacy: crypto_agent (mantener como backup hasta drop explícito)
- Tablas principales: lab_memory, lab_tasks, lab_projects, focus_checkins,
  diagnostics_log, token_candidates (1258 filas, 25 activos en lab_11mkeys)
- NOTA: detection_scores no existe como tabla separada — los scores están en token_candidates.detection_score
- crypto_agent.token_candidates quedó congelada en 2026-07-01 (pre-migración) — NO confundir con lab_11mkeys
- SIEMPRE usar -d lab_11mkeys en queries de agentes del Lab
- NUNCA dropear crypto_agent sin aprobación explícita de Marce

## Restricciones críticas del VPS — LEER ANTES DE ACTUAR

### Comandos PROHIBIDOS (se cuelgan indefinidamente)
- `docker logs [container]` — SE CUELGA, nunca usar
- `docker compose logs` — SE CUELGA, nunca usar
- `docker compose exec postgres` — SE CUELGA, nunca usar

### Comandos SEGUROS equivalentes
- Logs: `docker inspect CONTAINER --format='{{.LogPath}}' | xargs sudo tail -N`
- DB: `timeout 10 docker exec crypto_agent_system-postgres-1 psql -U postgres -d lab_11mkeys -c "QUERY"`
- Redis: `timeout 5 docker exec crypto_agent_system-redis-1 redis-cli [cmd]`
- Containers: `docker ps | awk 'NR>1 {print $NF, $7}'`
- Discovery heartbeat: `timeout 5 docker exec crypto_agent_system-redis-1 redis-cli GET discovery:last_run`

### Build y deploy
- Build: `docker build -f /opt/crypto_agent_system/agents/SERVICE/Dockerfile -t crypto_agent_system-SERVICE:latest /opt/crypto_agent_system`
- Build largo (numpy/sklearn): usar `nohup ... > /tmp/build_SERVICE.log 2>&1 &` para sobrevivir drops SSH
- Build con deps cambiadas: SIEMPRE `--no-cache` — Docker puede usar cache stale aunque requirements.txt cambió
- Restart: `docker restart crypto_agent_system-SERVICE-1`
- NUNCA usar `docker compose build` — el compose tiene error de validación en v5.1.3
- IMPORTANTE: smartdevops, scorer y learner NO están en docker-compose.yml — son containers standalone

### n8n
- Modelo Claude: siempre `claude-sonnet-4-6` (claude-sonnet-4-20250514 devuelve 404)
- Telegram node: siempre typeVersion 1.2 + additionalFields: {}
- SSH node: resource: "command", operation: "execute", credencial sshPassword
- `docker ps --format "{{.Names}}"` rompe n8n — usar awk
- Update workflow: PUT /api/v1/workflows/{id} con {name, nodes, connections, settings}
- settings solo: {"executionOrder":"v1"}
- N8N_API_KEY en /opt/crypto_agent_system/.env

## Protocolo obligatorio — Code Agent
1. Diagnóstico antes de acción — solo lectura antes de proponer cambios
2. Diff obligatorio — nunca sobrescribir sin mostrar diff y esperar aprobación
3. Sin commits ni push sin aprobación explícita
4. Deploy de un servicio a la vez
5. No reportar "completado" con errores activos
6. Mensajes conversacionales no invocan herramientas de modificación

## Stack completo
n8n · Claude API · Telegram bots · PostgreSQL · Redis · Docker · Python · GitHub

## Infraestructura n8n
- Dominio: https://n8n.11mkeys.ai
- SSL: Let's Encrypt, vence 2026-08-30, renovación automática
- Nginx reverse proxy a localhost:5678
- N8N_API_KEY guardada en /opt/crypto_agent_system/.env
- PATRÓN OBLIGATORIO para bots nuevos: nunca n8n-nodes-base.telegramTrigger —
  usar Webhook genérico + secret propio (ver Lección 15). Webhooks y secrets
  vigentes de cada bot están en su sección dentro de "Agentes operativos".

## INVENTARIO DE INFRAESTRUCTURA (verificado 2026-07-19 — `docker ps -a` completo)

### Containers Docker (16 reales)
| Container | Función | Puerto | Uptime | Token Telegram | Estado |
|---|---|---|---|---|---|
| crypto_agent_system-postgres-1 | DB (lab_11mkeys) | 5432 | 6 semanas | — | healthy |
| crypto_agent_system-redis-1 | Cache / bus / heartbeats | 6379 | 6 semanas | — | healthy |
| crypto_agent_system-n8n-1 | Orquestación workflows | 5678 | 5 días | — | ok |
| crypto_agent_system-grafana-1 | Dashboards métricas | 3000 | 6 semanas | — | ok — sin alert rules configuradas |
| crypto_agent_system-prometheus-1 | Métricas | 8000→9090 | 6 semanas | — | ok — sin alerting rules |
| crypto_agent_system-orchestrator-1 | Supervisor liviano 60s + market analysis | 8080 | recreado 2026-07-19 | 8766465123 (correcto) | ok |
| crypto_agent_system-dashboard-1 | Dashboard web (JWT) | 8001 | — | 8766465123 (correcto) | ok |
| crypto_agent_system-smartdevops-1 | Diagnóstico IA 30min + fixes propuestos | — | — | 8766465123 (correcto)¹ | ok |
| crypto_agent_system-narrative-research-1 | Narrative Swing — research agent | — | — | 8766465123 (correcto) | ok |
| crypto_agent_system-discovery-1 | Descubrimiento de tokens (1×/día 02:00 UTC) | — | — | 8766465123 (correcto) | ok |
| crypto_agent_system-monitor-1 | Monitoreo precio/volumen (~5 min) | — | recreado 2026-07-19 | 8766465123 (correcto) | ok |
| crypto_agent_system-detector-1 | Detección de señales | — | recreado 2026-07-19 | 8766465123 (correcto) | ok |
| crypto_agent_system-scorer-1 | Scoring combinado | — | 2 días | 8766465123 (correcto) | ok |
| crypto_agent_system-executor-1 | Ejecución de trades (paper) | — | recreado 2026-07-19 | 8766465123 (correcto) | ok |
| crypto_agent_system-learner-1 | Aprendizaje post-trade | — | 2 días | 8766465123 (correcto) | ok |
| focus_guardian | Check-ins personales (Focus Guardian) | — | 3 semanas | — (usa FOCUS_BOT_TOKEN) | ok |

¹ smartdevops usa además `SMARTDEVOPS_BOT_TOKEN` (8141614556) intencionalmente — ese es su bot propio.

**✅ Resuelto (2026-07-19):** `monitor-1`, `detector-1` y `executor-1` tenían el token viejo de
Telegram (8141614556) en su entorno — confirmado inofensivo (ninguno de los tres importa nada
relacionado a Telegram, el campo es inerte, solo obligatorio para instanciar `Settings`).
Recreados igual con `stop+rm+run --env-file` para no arrastrar `.env` desactualizado a futuro.
Al recrear `detector` y `executor` (imágenes del 2026-07-04) apareció un bug real y distinto:
`ModuleNotFoundError: sentry_sdk` primero, luego `pydantic_settings` — imágenes stale, mismo
patrón que el orchestrator (Lección 9: cache de build ignora cambios de `requirements.txt`).
Fix: guard `try/except ImportError` en `sentry_sdk` (ya prescrito en Lección 10, ahora aplicado
también a `monitor`/`detector`/`executor`, no solo a los que ya lo tenían) + rebuild `--no-cache`
de `detector` y `executor` (`monitor` no lo necesitó, su imagen ya tenía las deps al día).

### Bots de Telegram — qué token, quién lo usa, qué canal
| Bot | Var en .env | Usado por | Canal |
|---|---|---|---|
| @CryptoAgentBot (bot_id 8766465123) | TELEGRAM_BOT_TOKEN | scorer, learner, monitor, detector, executor, orchestrator, dashboard, discovery, narrative-research | Trading (Criminal Pumps ⚡ + Narrative Swing 🌊) — notificaciones y consultas (mismo webhook que PM Bot, ver "PM Agent") |
| @ElevenMkeys_SmartDevops_bot (8141614556) | SMARTDEVOPS_BOT_TOKEN | smartdevops-1 (único uso correcto) | Diagnóstico IA — botones sd_approve/sd_ignore |
| @ElevenMkeys_PM_Bot (8818804931) | — (n8n, no en .env de containers) | n8n workflow PM Agent | Gestión del Lab (tareas, proyectos, finanzas, memoria) |
| @ElevenMkeys_Advisor_bot | ADVISOR_BOT_TOKEN | n8n workflow Strategy Advisor | Diagnóstico y escalado a Task Runner |
| @ElevenMkeys_MonkeyBrain_bot | MONKEY_BRAIN_BOT_TOKEN | n8n workflow Monkey Brain | Captura de insights |
| @ElevenMkeys_CodeAgent_bot | — (n8n) | n8n workflow Code Agent | Fixes de código con aprobación |
| @ElevenMkeys_Focus_bot | FOCUS_BOT_TOKEN | focus_guardian | Check-ins personales |

*monitor tiene el token viejo — en teoría debería usar TELEGRAM_BOT_TOKEN como scorer/learner.

### Workflows n8n activos (10, verificado 2026-07-19)
Ver detalle completo en "Agentes operativos" abajo. Todos `active=true`:
Finance Alerts · Task Runner · Strategy Advisor · PM Agent · Code Agent · Advisor Report ·
Advisor Notify · SmartDevops Agent · Weekly Board Agent · Monkey Brain.

## Agentes operativos — Bots y Workflows

### Strategy Advisor
- Bot: @ElevenMkeys_Advisor_bot
- Workflows: 7Ohb4fekhWkgfMVE (Telegram, 51 nodos desde B9) + mDjJw4IIFJhnZq1j (notify) + mB0dJy17gxM4V3FN (report)
- Función: Director de operaciones. Diagnostica el sistema. Escala al Task Runner si detecta fix necesario.
- Credencial n8n: OnOkrq5xaWWl9e9j
- Webhook: https://n8n.11mkeys.ai/webhook/advisor-telegram (Webhook genérico, ver Lección 15)
- Secret: ADVISOR_WEBHOOK_SECRET en .env
- **Memoria conversacional (B9, 2026-07-20/21):** contexto rodante entre sesiones — NO es un log
  append-only, es UNA clave en `lab_memory` que Claude reescribe completa en cada turno relevante.
  - Clave: `advisor_conversation_context` (tipo `estrategica`, agente `strategy_advisor`,
    proyecto `null` — transversal). Formato: DECISIONES VIGENTES / TEMAS ABIERTOS / PRÓXIMOS
    PASOS / ÚLTIMO INTERCAMBIO, máx ~2000 caracteres, se sobreescribe entera (no se acumula).
  - Lectura: nodo `Q Advisor Context` (SSH, `SELECT valor ... LIMIT 1`) insertado en la cadena
    `SSH Ctx Advisor → Q Advisor Context → Build Advisor Body`; se antepone al prompt como
    sección "HILO CONVERSACIONAL PREVIO".
  - Escritura: Claude agrega la clave `context_update` (null si no hubo cambios de estado) al
    mismo bloque JSON que ya usaba para `type`/`task_spec`. Rama nueva en paralelo desde
    `Parse Advisor Resp` (no toca la conexión existente a `IF Needs Fix`):
    `Should Update Context → Prep Conv Context → Write Conv Context` (UPSERT vía
    `DO $$ UPDATE ... IF NOT FOUND THEN INSERT $$` — no hay índice único en `clave` de
    `lab_memory`, se evitó agregar uno). Dispara sin importar el camino final de la respuesta
    (escalar/diagnosticar/directo) porque lee del JSON de la primera llamada a Claude.
  - Verificado end-to-end con mensajes reales (no simulación): decisión de prueba registrada,
    recordada en un mensaje separado sin repreguntar, y limpiada — los 3 pasos con
    `context_update` comportándose correctamente (escribe/null/reescribe).

### Monkey Brain
- Bot: @ElevenMkeys_MonkeyBrain_bot
- Token: en .env como MONKEY_BRAIN_BOT_TOKEN
- Workflow: uBR0ICIj2ZtLUCvk (50 nodos)
- Webhook: https://n8n.11mkeys.ai/webhook/monkeybrain-telegram (Webhook genérico, ver Lección 15)
- Secret: MONKEYBRAIN_WEBHOOK_SECRET en .env
- Función: Captura insights, investiga con web_search, scheduler 48h, conecta ideas

### PM Agent
- Bot: @ElevenMkeys_PM_Bot (bot_id 8818804931)
- Token: 8818804931:AAGYdiaWTx-rr_M0sMxRUJzN9Gy05bbH9Fc
- Workflow: XcHapUoJvZvl8kLs "11Mkeys PM Agent" (111 nodos) — reemplaza a HlY3gLWuJowyITB9
  (eliminado 2026-07-14, quedó en estado irrecuperable donde activate() nunca
  volvía a registrar el webhook — ver Lección 15)
- Webhook: https://n8n.11mkeys.ai/webhook/pm-agent-telegram (Webhook genérico, ver Lección 15)
- Secret: PM_WEBHOOK_SECRET en .env
- Credencial: "11Mkeys PM Bot" id JGUqhrTxSR2RjdYy
- IMPORTANTE: este mismo webhook recibe TAMBIÉN los mensajes del CryptoAgentBot
  (TELEGRAM_BOT_TOKEN) — no son bots técnicamente separados a nivel n8n, el
  routing (Route Command switch) es lo que separa comandos de gestión del Lab
  de comandos de trading. Ver "Narrative Swing — Dashboard y comandos" abajo.
- Comandos Lab: /estado /tareas /proyectos /blockers /nueva [desc] #[proyecto] /done [id]
           /run [cmd] /memoria [clave|hoy|proyecto X] /ingreso /finanzas /nuevo_proyecto
- Comandos Narrative Swing (tag 🌊): /narrative (candidatos) · /trades_ns (posiciones paper)
           · /gate (progreso al gate de producción) · nsm_approve_[symbol] / nsm_reject_[symbol]
- Comandos Criminal Pumps (tag ⚡): /pumps (estado watchlist)

### Narrative Swing — Dashboard y convención de canales
- Dashboard web: http://167.88.33.68:8001/static/narrative.html (link "🌊 Narrative Swing"
  en la nav del dashboard principal). Requiere login JWT (mismo que el dashboard general).
  Endpoints: GET /narrative/candidates · /narrative/trades · /narrative/gate
  (montados sin prefijo /api, igual que el resto de los routers del dashboard — ver
  agents/dashboard/routers/narrative.py en crypto_agent_system)
- Convención de canales Telegram (decisión de Marce 2026-07-13): PM Bot = gestión del
  Lab (tareas, proyectos, finanzas, memoria). CryptoAgentBot = trading (Criminal Pumps ⚡
  + Narrative Swing 🌊), notificaciones Y consultas. Todo mensaje de trading lleva tag
  de sistema (🌊 NARRATIVE SWING / ⚡ CRIMINAL PUMPS) — aplicado en
  agents/scorer/message_formatter.py, agents/learner/metrics_reporter.py y
  agents/narrative/notifier.py (crypto_agent_system).
- Gate de producción Narrative Swing: 30 días · 10 trades cerrados · win rate ≥55% ·
  profit factor ≥1.3. Progreso visible en /gate (bot) o el dashboard.

### Task Runner
- Workflow: 2vlG13sLx4bXAY86 (18 nodos)
- Webhook: https://n8n.11mkeys.ai/webhook/task-runner
- Función: Recibe spec técnica, genera fix via Claude, aplica diff, Aprobar/Rechazar
- Backup automático: .tr_bak antes de cada modificación
- Redis key: tr:pending para estado

### Code Agent
- Bot: @ElevenMkeys_CodeAgent_bot
- Token: 8763657547:AAHBZoVejJnmYbg2n0gmOqQ48nLmqPjfvqM
- Workflow: YJSrUZ9I6wuLt79v (26 nodos)
- Webhook: https://n8n.11mkeys.ai/webhook/codeagent-telegram (Webhook genérico, ver Lección 15)
- Secret: CODEAGENT_WEBHOOK_SECRET en .env
- Comandos: /fix_etherscan /status /logs /scores · approve_deploy · reject_deploy

### SmartDevops Agent
- Bot: @ElevenMkeys_SmartDevops_bot
- Token: 8141614556:AAEbY07qhTW0idh5BaH5fMjv2JPt2PY1mV0 — en .env como SMARTDEVOPS_BOT_TOKEN
- Workflow: qEN2uvjywgpB5jaN (9 nodos)
- Webhook: https://n8n.11mkeys.ai/webhook/smartdevops-telegram (Webhook genérico, ver Lección 15)
- Secret: SMARTDEVOPS_WEBHOOK_SECRET en .env
- Función: Ciclo 30min, Docker API + PostgreSQL + Redis, propone fixes con sd_approve/sd_ignore
- Historial en: diagnostics_log (PostgreSQL)
- Container standalone (no en docker-compose.yml) — recrear con docker run + --env-file

### Orchestrator (supervisor liviano — no tiene bot propio)
- Container: `crypto_agent_system-orchestrator-1`, puerto 8080, red `crypto_agent_network`
- No bind-mount de `alembic/` ni `alembic.ini` — quedan horneados en la imagen (`COPY` en el
  Dockerfile). Si se agrega una migración nueva, esta imagen queda desactualizada en silencio
  hasta el próximo restart/recreate — rebuildear con `--no-cache` junto con cualquier migración
  nueva, no solo cuando cambia `requirements.txt` (ver Lección 23).
- Función: `orchestrator/agent_supervisor.py` — supervisor liviano (sin LLM) que chequea
  actividad de discovery/monitor/detector/scorer/executor/learner/dashboard vía DB/Redis/HTTP
  cada 60s (`monitor_loop`, intencional — es barato, sin costo de API). Manda alerta Telegram
  (`TELEGRAM_BOT_TOKEN`, no el de SmartDevops) con cooldown de 1h (`supervisor:alert_cooldown:*`
  en Redis) cuando algo queda `unhealthy`.
- División de roles con SmartDevops: orchestrator detecta caídas rápido y barato (60s, sin IA);
  SmartDevops diagnostica causas y propone fixes cada 30 min (con Claude, más caro/lento).
- Dashboard health check: `settings.dashboard_health_url` (compartido con SmartDevops) —
  `http://crypto_agent_system-dashboard-1:8001/health`. El hostname corto `dashboard` NO
  resuelve en `crypto_agent_network` — usar siempre el nombre completo del container.
- Historial: ver sesión 2026-07-18/19 en Bitácora — este servicio no estaba documentado acá y
  fue la fuente real de un spam de alertas que se le atribuyó a SmartDevops por varias sesiones.

### Focus Guardian
- Bot: @ElevenMkeys_Focus_bot
- Token: en .env como FOCUS_BOT_TOKEN
- Container: focus_guardian en crypto_agent_network
- Tabla: focus_checkins
- Scheduler UTC: check-in mañana 12:00 | timeout 14:00 | check-in noche 00:00

### Weekly Board Agent
- Workflow: rJzmIz9h7XHDymGB (10 nodos)
- Schedule: domingos 13:00 UTC
- Entrega: chat_id 6517856768 via PM Bot (cred JGUqhrTxSR2RjdYy)
- Incluye: foco semanal, tokens top, containers, alertas, tareas, finanzas, workflows

### Finance Agent
- Integrado en PM Agent
- Comandos: /ingreso [proyecto] [monto] [descripción] · /finanzas
- Finance Alerts: workflow propio, lunes 09:00 UTC
- Proyectos válidos: crypto_agent · nodeflow · depin · estrategia_b · 11mkeys_lab

### Monkey Advisor - Consultas (ARCHIVADO 2026-07-14)
- Workflow eliminado de n8n. Compartía el bot @MonkeyAdvisor_11Mkeys_bot con
  Code Agent — un bot solo puede tener un webhook activo, y el real quedaba
  registrado a Code Agent, así que este workflow nunca recibió tráfico.
  Usaba además convenciones obsoletas (docker compose exec/ps, DB crypto_agent
  en vez de lab_11mkeys). Sin funcionalidad única frente a Monkey Brain.
- Backup completo: /opt/11mkeys_lab/archive/monkey_advisor_consultas_20260713.json
- Detalle: lab_memory clave monkey_advisor_consultas_archivado

## lab_memory — Memoria RAG compartida
- Tabla: lab_memory en lab_11mkeys
- Tipos: operativa | estrategica | aprendizaje | insight
- Ciclo obligatorio de todos los agentes: LEER antes de actuar → ACTUAR → ESCRIBIR al finalizar
- Acceso: /memoria [clave|hoy|proyecto X] desde PM Bot
- Curador: Strategy Advisor (marca vigente=false cuando registros quedan obsoletos)

### Query RAG estándar
```sql
SELECT tipo, agente, clave, LEFT(valor,400), proyecto, creado_en::date
FROM lab_memory
WHERE vigente = true
  AND (tipo = 'aprendizaje'
    OR creado_en > NOW() - INTERVAL '24 hours'
    OR (tipo = 'estrategica' AND proyecto IS NOT NULL))
ORDER BY CASE tipo WHEN 'aprendizaje' THEN 1 WHEN 'estrategica' THEN 2
  WHEN 'operativa' THEN 3 ELSE 4 END, creado_en DESC
LIMIT 15;
```

## lab_projects — Proyectos del Lab
- Tabla: lab_projects en lab_11mkeys
- Proyectos válidos: 11mkeys_lab (default) · crypto_agent · nodeflow · depin · estrategia_b
- Columnas: id, nombre, titulo, descripcion, status, fase, bloqueante, gate_salida, agentes

## Proyectos en el VPS
- /opt/crypto_agent_system — Crypto Agent System (rama main)
  IMPORTANTE: historial divergente con origin — NO usar git reset --hard
  Git pull seguro: git fetch origin main && git merge origin/main
- /opt/11mkeys_lab — Lab projects (rama master, alineado con origin)

## CPU/memoria limits (docker-compose.yml)
| Servicio | CPUs | Memoria |
|---|---|---|
| monitor | 0.50 | 512m |
| detector | 0.30 | 256m |
| scorer | 0.30 | 256m |
| orchestrator | 0.30 | 256m |
| smartdevops | 0.50 | 256m |
| n8n | 1.00 | 1g |

## Lecciones aprendidas — NO repetir estos errores

1. docker logs se cuelga — usar docker inspect + tail (ver restricciones)
2. n8n campo sin prefijo = — los {{ }} son texto literal sin el =, no expresiones
3. APScheduler 3.x + Python 3.11 — no awaitea async functions directamente,
   usar wrapper síncrono: asyncio.get_running_loop().create_task(coro())
4. lab_memory debe apuntar a -d lab_11mkeys, nunca a -d crypto_agent
5. crypto_agent rama main tiene historial divergente — nunca git reset --hard
6. docker ps --format "{{.Names}}" rompe n8n — usar awk
7. n8n Telegram node typeVersion 1 da 400 Bad Request — usar 1.2
8. docker restart NO re-lee .env — para picar cambios de variables hay que
   docker stop + rm + run --env-file /opt/crypto_agent_system/.env
9. Docker build cache ignora cambios en requirements.txt — usar --no-cache
   cuando se restaura o modifica requirements.txt; verificar con docker run --rm IMAGE pip list
10. import sentry_sdk directo crashea si el package falta — siempre usar
    try/except ImportError con sentry_sdk=None; afecta detector/discovery/executor/monitor
    si se reconstruyen sus imágenes
11. n8n Telegram node SIEMPRE fuerza parse_mode=Markdown aunque additionalFields={} —
    si el texto tiene ** o _ sin cerrar → "Bad request: can't parse entities".
    Fix: en additionalFields poner {"appendAttribution": false} y en el nodo Code
    previo escapar `**` → `*` y remover headers `#` antes de enviar.
    Detectado 2026-07-10 inspeccionando GenericFunctions.js del node.
12. n8n HTTP Request node: sendHeaders debe ser True explícitamente — si queda en None,
    los headerParameters (x-api-key, etc.) no se envían aunque estén definidos.
    Causa "Authorization failed" inmediato (< 300ms). Comparar siempre vs nodo equivalente
    que sí funciona para detectar la diferencia.
13. n8n HTTP Request node: sendBody también debe ser True explícitamente para POST con body.
    sendHeaders y sendBody son flags independientes. Sin sendBody=True el POST llega sin body
    → Anthropic devuelve 400 "Bad request". El nodo puede tener specifyBody+body correctos
    y aun así no enviar nada si sendBody está ausente.
14. Pasar código JS con $ por SSH heredoc: los $ se expanden por el shell aunque uses
    << 'MARKER' si el código está en la sección quoted del comando SSH. Solución: escribir
    el JS a un archivo vía cat << 'RAWEOF' (heredoc single-quoted remoto) usando solo
    double-quotes en el JS, luego aplicar PUT con Python leyendo el archivo.
15. n8n-nodes-base.telegramTrigger: activate() (vía API o vía toggle de la UI) no
    siempre llama a setWebhook de Telegram, aunque el workflow quede active=true y
    registre la ruta interna en webhook_entity. Bug reproducible en n8n 2.22.5, no
    logea ningún error. Síntoma: getWebhookInfo muestra url vacía, o 403 "secret
    inválido" pese a active=true y ruta registrada. Probado sin éxito: toggle API,
    toggle UI, editar el nodo a mano, reiniciar el container completo, duplicar el
    workflow entero. SOLUCIÓN DEFINITIVA (no usar telegramTrigger nunca más):
      1. Reemplazar el nodo Telegram Trigger por n8n-nodes-base.webhook
         (httpMethod POST, path fijo legible ej. "pm-agent-telegram",
         responseMode onReceived).
      2. Agregar un nodo Code inmediatamente después que valide el secret y
         normalice el body:
         const secret = ($json.headers||{})['x-telegram-bot-api-secret-token'];
         const expected = '<SECRET>'; // guardado en .env como {BOT}_WEBHOOK_SECRET
         if (secret !== expected) return [];
         return [{ json: $json.body }];
      3. Registrar el webhook a mano (n8n nunca lo hace solo para este tipo de nodo):
         curl -X POST https://api.telegram.org/bot{TOKEN}/setWebhook -H
         "Content-Type: application/json" -d '{"url":"https://n8n.11mkeys.ai/webhook/
         {path}","secret_token":"{SECRET}","allowed_updates":["message","callback_query"]}'
      4. CRÍTICO: el nodo Code de validación debe quedarse con el NOMBRE ORIGINAL
         del Telegram Trigger que reemplaza (ej. "Telegram Trigger"), no el nodo
         Webhook. Otros nodos del workflow pueden referenciarlo por nombre vía
         $('Telegram Trigger').json... y esas referencias se rompen si se renombra
         — detectado en Code Agent, nodo "Send a text message" fallaba con
         "Referenced node doesn't exist" hasta corregir el nombre.
      5. Un bot de Telegram solo admite un webhook activo — si dos workflows
         comparten credencial, solo uno recibe tráfico real (causa real de que
         Monkey Advisor - Consultas nunca funcionara, ver sección de agentes).
    Aplicado 2026-07-13/14 a los 5 bots del Lab con Telegram Trigger: PM Agent,
    Strategy Advisor, Monkey Brain, SmartDevops Agent, Code Agent. El Task Runner
    (2vlG13sLx4bXAY86) ya usaba Webhook genérico desde el inicio — no necesitó
    migración. Todo bot nuevo debe nacer con este patrón, nunca telegramTrigger.
16. psql con `-t -A` (tuples-only, unaligned) SIGUE imprimiendo las líneas de status
    de comandos DML sin resultado ("UPDATE 0", "INSERT 0 0") cuando 0 filas matchean
    — no es un output vacío, es texto no-vacío interpretado erróneamente como "sí hubo
    resultado" en nodos Code que solo chequean `if (!raw)`. Fix: agregar también `-q`
    (quiet) — con `-q -t -A` el output es realmente vacío cuando no hay filas. Detectado
    2026-07-16 en el workflow de Narrative Swing (un símbolo inexistente se reportaba
    como "archivado" con éxito). Aplicar `-q` siempre que el output de psql se parsea
    programáticamente en un nodo Code.
17. INYECCIÓN DE SHELL vía contenido de LLM: si un comando SSH arma `psql -c "SQL con
    ${contenido_de_claude} interpolado"` y ese contenido trae una comilla doble, el
    shell corta el argumento ahí mismo y el resto del texto se ejecuta como comandos/
    argumentos de shell sueltos (visto en vivo: "docker: 'docker logs' requires 1
    argument", palabras del texto de Claude tratadas como comandos). Pasa con
    cualquier texto largo de LLM insertado en un `-c "..."` de shell, no solo casos
    raros — prosa normal trae comillas dobles seguido. FIX OBLIGATORIO para cualquier
    INSERT/UPDATE con contenido largo/libre de un LLM: no interpolar en `-c "..."`.
    En su lugar, base64 + stdin: `echo '${base64_del_sql}' | base64 -d | timeout 10
    docker exec -i crypto_agent_system-postgres-1 psql -U postgres -d lab_11mkeys`
    (Buffer.from(sql,'utf-8').toString('base64') en el nodo Code). El shell nunca ve
    el contenido crudo. Detectado y corregido 2026-07-16 en Monkey Brain (Build SQL).
    Auditar cualquier otro nodo que inserte texto libre de Claude/LLM a la DB via SSH.
18. Telegram Markdown v1 (parse_mode Markdown) rompe con "can't parse entities" no solo
    por `**`/`_` sin cerrar (Lección 11) sino por CUALQUIER `[texto]` sin `(url)`
    inmediatamente después (se interpreta como link incompleto) y por underscores
    sueltos en texto propio del bot, no solo contenido de LLM — ej. mencionar el
    comando `/trades_ns` literal en un mensaje rompe el parseo porque `_` abre itálica.
    Fix para texto fijo (no generado por LLM): envolver en backticks (`` `/trades_ns` ``)
    — los code-spans de Markdown no parsean formato anidado. Para corchetes literales
    tipo "[L1]", usar paréntesis "(L1)" en su lugar. Detectado 2026-07-16 construyendo
    los comandos /narrative del Narrative Swing Module.

19. APScheduler AsyncIOScheduler + Python 3.11: la Lección 3 (usar wrapper síncrono +
    asyncio.get_running_loop().create_task()) es INCORRECTA para AsyncIOScheduler
    específicamente. AsyncIOExecutor corre callables *síncronos* en un thread pool sin
    loop propio — el wrapper sync explota con "RuntimeError: no running event loop"
    apenas se ejecuta el primer disparo del cron (no al agendar, no al arrancar el
    agente). Por eso pasó desapercibido: el agente arranca bien, el heartbeat previo
    da "ok" (de un run manual o de startup), y recién falla en el próximo disparo
    programado. FIX CORRECTO: pasar la coroutine function DIRECTO a
    scheduler.add_job(self.run, trigger="cron", ...) sin wrapper — AsyncIOExecutor sí
    sabe ejecutar coroutine functions correctamente dentro del loop principal (patrón
    ya usado por monitor_agent.py y research_agent.py). Bug real: discovery_agent.py
    rompía el cron diario de las 02:00 UTC desde el 30/6 sin que nadie lo notara — el
    heartbeat en Redis se escribe al FINAL de run(), así que un run() que nunca arrancó
    tampoco escribe heartbeat nuevo, pero el TTL del heartbeat anterior (de un run
    manual o startup) lo dejaba en "ok" por horas, ocultando el problema. Detectado
    2026-07-17 por el propio Strategy Advisor leyendo logs reales (no por monitoreo de
    heartbeat). Auditar cualquier otro agente con patrón `_scheduled_run` + wrapper sync.

20. n8n Code node después de un nodo Telegram: el output de un nodo Telegram REEMPLAZA
    $json con la respuesta cruda de la API de Telegram (`{ok, result: {message_id,
    chat: {id, ...}, text, ...}}`) — NO conserva los campos que traía el item de
    entrada (ej. chat_id calculado antes). Cualquier nodo Code/SSH encadenado
    directamente después de un nodo Telegram que necesite datos previos (chat_id,
    etc.) debe leerlos con $('NodoAnteriorAlTelegram').first().json.campo, nunca
    $json.campo. Bug real: un nodo SSH que hacía `redis-cli DEL clave:{{ $json.chat_id
    }}` encadenado después de un Telegram Send devolvía "0" (cero keys borradas)
    porque $json.chat_id era undefined — el comando corría como `DEL clave:` (chat_id
    vacío) sin error visible, silenciosamente no borraba nada. Detectado 2026-07-17
    construyendo el patrón de estado pendiente en Redis del Strategy Advisor
    (advisor:pending:{chat_id}, mismo patrón que mb:state:{chat_id} de Monkey Brain).

21. Al investigar "qué está mandando este mensaje/alerta", pedir el TEXTO LITERAL (copy-paste
    exacto, con emojis/formato) antes de seguir descartando candidatos por código es más rápido
    que adivinar — el formato exacto de un mensaje fijo/templateado identifica al emisor real
    de inmediato y evita atribuírselo por asociación al servicio "obvio" (ej. un mensaje de
    alerta genérico atribuido a SmartDevops porque "suena a eso", cuando en realidad venía de
    un servicio de supervisión distinto y sin documentar). Detectado 2026-07-18/19.
22. Al buscar la fuente de algo inesperado, correr `docker ps -a` completo (sin filtrar por
    nombre esperado) — puede haber containers corriendo hace semanas sin estar documentados en
    este archivo. El VPS tenía 15 containers reales; `orchestrator` (puerto 8080, agente
    supervisor propio con sus propias alertas Telegram) no figuraba en ningún lado.
23. `docker restart` no relee `.env` (Lección 8) — pero además, si un container lleva mucho
    tiempo sin recrearse, un `stop+rm+run` para picar el `.env` correcto puede exponer un
    SEGUNDO problema latente: código/migraciones nuevas que nunca se ejecutaron porque el
    proceso nunca volvió a arrancar desde cero. Si el Dockerfile del servicio hornea `alembic/`
    en la imagen (no bind-mount), cualquier migración agregada después del último build queda
    invisible para ese container hasta un rebuild `--no-cache` — el síntoma es
    `alembic.util.messaging: Can't locate revision identified by 'XXXX'` con la DB ya en esa
    revisión (aplicada por otro servicio) pero la imagen sin el archivo. Antes de cualquier
    `stop+rm+run` en un container con semanas de uptime, considerar rebuildear primero.
24. Extensión de Lección 10 (`import sentry_sdk` sin guardia): el guard `try/except
    ImportError` se había aplicado en su momento solo a los agentes donde el bug ya se había
    manifestado, no a los 4 nombrados explícitamente en la lección (`detector/discovery/
    executor/monitor`). Al recrear `detector` y `executor` (containers de semanas de uptime,
    imágenes del 2026-07-04) el bug apareció recién ahí — y en cascada, DESPUÉS de arreglar
    `sentry_sdk` apareció un segundo `ModuleNotFoundError: pydantic_settings`, síntoma de que
    la imagen entera estaba stale, no solo un import puntual. Regla general: cuando un
    `stop+rm+run` en un container de larga vida revela UN `ModuleNotFoundError`, no asumir que
    es el único — la imagen puede tener varias dependencias desactualizadas en cascada;
    rebuildear `--no-cache` con el `requirements.txt` actual en vez de parchear import por
    import. Aplicar el guard de Lección 10 preventivamente a los 4 agentes nombrados,
    aunque no hayan fallado todavía (ej. `monitor` no falló esta vez, pero tiene el mismo
    import sin protección — solo tuvo suerte con el estado de su imagen).

## Estado del sistema (actualizado 2026-07-11)
- Monitor: 81 tokens activos, ciclo ~5 min
- ALERT_THRESHOLD: **28** (ajustado 2026-07-07, era 65 → 43 → 28)
  - Tokens sin chain/contract_address → `executor_agent.no_chain_skip` (intencional, Fix 2 anti-stablecoin)
  - Tokens con chain: max detection_score ~30, composite_score por ciclo fluctúa cerca del threshold
  - Tokens de alto score (RTM 64.5, ROPRA 58.06, RCRCL 59.5) son PoW nativos sin contrato EVM
  - Próximo trade esperado cuando ROBO u otro token con chain supere 28 en un ciclo
- Último trade: 2026-07-01 (RCLOI/ROPRA/RFLHY con scores 61-67, pre-fix anti-stablecoin)
- paper_trading: true (todos los trades son simulados)

### Separación de tokens Telegram (completada 2026-07-08)
- `TELEGRAM_BOT_TOKEN` = 8766465123 (CryptoAgentBot) — scorer, learner, monitor, alertas de trading
- `SMARTDEVOPS_BOT_TOKEN` = 8141614556 (SmartDevops bot) — botones sd_approve/sd_ignore
- Commits: `5369f05` (separación) + `ecdfaa7` (sentry fix scorer/learner) en rama main

### Containers scorer/learner/smartdevops (reconstruidos 2026-07-08)
- Imágenes reconstruidas con `--no-cache` desde requirements.txt completo (restaurado de git c7e3386)
- Recreados con `docker run --env-file` para picar nuevas variables de entorno
- scorer:heartbeat activo en Redis (TTL ~127s confirmado)

## Reglas
- Nunca modificar /opt/crypto_agent_system sin diagnóstico previo
- Cada paso requiere confirmación antes de continuar
- Actualizar este archivo al finalizar cada sesión importante
- FAQ vive en /opt/11mkeys_lab/docs/FAQ.md — actualizar junto con fixes
