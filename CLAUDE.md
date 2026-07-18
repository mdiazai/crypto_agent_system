# CLAUDE.md — 11mkeys_lab
## Actualizado: 2026-07-16

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

## Agentes operativos — Bots y Workflows

### Strategy Advisor
- Bot: @ElevenMkeys_Advisor_bot
- Workflows: 7Ohb4fekhWkgfMVE (Telegram, 38 nodos) + mDjJw4IIFJhnZq1j (notify) + mB0dJy17gxM4V3FN (report)
- Función: Director de operaciones. Diagnostica el sistema. Escala al Task Runner si detecta fix necesario.
- Credencial n8n: OnOkrq5xaWWl9e9j
- Webhook: https://n8n.11mkeys.ai/webhook/advisor-telegram (Webhook genérico, ver Lección 15)
- Secret: ADVISOR_WEBHOOK_SECRET en .env

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
