# CLAUDE.md — 11mkeys_lab
## Actualizado: 2026-07-08

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
  diagnostics_log, token_candidates, detection_scores
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

## Agentes operativos — Bots y Workflows

### Strategy Advisor
- Bot: @ElevenMkeys_Advisor_bot
- Workflows: 7Ohb4fekhWkgfMVE (Telegram) + mDjJw4IIFJhnZq1j (notify) + mB0dJy17gxM4V3FN (report)
- Función: Director de operaciones. Diagnostica el sistema. Escala al Task Runner si detecta fix necesario.
- Credencial n8n: OnOkrq5xaWWl9e9j

### Monkey Brain
- Bot: @ElevenMkeys_MonkeyBrain_bot
- Token: en .env como MONKEY_BRAIN_BOT_TOKEN
- Función: Captura insights, investiga con web_search, scheduler 48h, conecta ideas

### PM Agent
- Bot: @ElevenMkeys_PM_Bot (bot_id 8818804931)
- Token: 8818804931:AAGYdiaWTx-rr_M0sMxRUJzN9Gy05bbH9Fc
- Workflow: HlY3gLWuJowyITB9 (81 nodos)
- Webhook: https://n8n.11mkeys.ai/webhook/20246b71-c0a8-4af5-a406-e93749e29524/webhook
- Credencial: "11Mkeys PM Bot" id JGUqhrTxSR2RjdYy
- Comandos: /estado /tareas /proyectos /blockers /nueva [desc] #[proyecto] /done [id]
           /run [cmd] /memoria [clave|hoy|proyecto X] /ingreso /finanzas /nuevo_proyecto

### Task Runner
- Workflow: 2vlG13sLx4bXAY86 (18 nodos)
- Webhook: https://n8n.11mkeys.ai/webhook/task-runner
- Función: Recibe spec técnica, genera fix via Claude, aplica diff, Aprobar/Rechazar
- Backup automático: .tr_bak antes de cada modificación
- Redis key: tr:pending para estado

### Code Agent
- Bot: @ElevenMkeys_CodeAgent_bot
- Token: 8763657547:AAHBZoVejJnmYbg2n0gmOqQ48nLmqPjfvqM
- Webhook: https://n8n.11mkeys.ai/webhook/c1a5e861-f106-4d7d-82e2-0be00cc13a7c/webhook
- Comandos: /fix_etherscan /status /logs /scores · approve_deploy · reject_deploy

### SmartDevops Agent
- Bot: @ElevenMkeys_SmartDevops_bot
- Token: 8141614556:AAEbY07qhTW0idh5BaH5fMjv2JPt2PY1mV0 — en .env como SMARTDEVOPS_BOT_TOKEN
- Webhook: https://n8n.11mkeys.ai/webhook/4e2d5c25-11ce-476c-85c7-d45f847f168c/webhook
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

### Monkey Advisor (legacy)
- Bot: @MonkeyAdvisor_11Mkeys_bot
- Token: 8829243525:AAGvN7WJsGbM3Hfg0uDAPUog38yALBOghdQ
- Webhook: https://n8n.11mkeys.ai/webhook/4ddb16b8-171d-4811-8da5-65e99b4ee153/webhook

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

## Estado del sistema (actualizado 2026-07-08)
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
