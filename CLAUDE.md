# CLAUDE.md — crypto_agent_system

## Descripción
Sistema multi-agente de detección y ejecución automática de 
"Criminal Pumps" en criptomonedas.

## Stack
Python 3.11, asyncio, FastAPI, Redis, PostgreSQL, 
CCXT (MEXC + Bitget), Claude API, Docker

## Archivos de referencia
- MASTER_PROMPT_CryptoAgent.md — plan de construcción completo
- BLUEPRINT_CryptoAgent.md — arquitectura y contexto de negocio

## Estado de fases
- [x] Fase 0 — Setup inicial (estructura, Docker, .env)
- [x] Fase 1 — Shared layer (modelos PostgreSQL + Redis bus)
- [x] Fase 2 — Agente Discovery
- [x] Fase 3 — Agente Monitor
- [x] Fase 4 — Agente Detector
- [x] Fase 5 — Agente Scorer + Telegram
- [x] Fase 6 — Agente Executor + Risk Manager
- [x] Fase 7 — Agente Learner
- [x] Fase 8 — Dashboard API (backend)
- [x] Fase 9 — Orchestrator
- [x] Fase 10 — Tests
- [x] Fase 11 — Frontend/UI del Dashboard (HTML + Chart.js + Alpine.js, puerto 8001)
- [x] Fase 12 — Pantalla Performance (GET /performance/metrics + performance.html)
- [x] Fase 13 — On-chain multi-fuente: Coinglass + Etherscan + CryptoQuant

## Reglas globales
- Todo el código debe ser async
- PAPER_TRADING=true por defecto, nunca cambiar sin 30 días de datos
- Nunca hardcodear credenciales, siempre desde .env
- Type hints en todo el código
- structlog para logging

## Estado del deploy (Docker)
- Dashboard UI: http://localhost:8001 (admin / admin1234)
- Orchestrator:  http://localhost:8080/health
- Grafana:       http://localhost:3000 (admin / admin)
- Prometheus:    http://localhost:8000

## Configuración activa (2026-05-15)
- ALERT_THRESHOLD=60 (docker-compose override; .env tiene 62 — actualizar manualmente)
- MAX_HOLD_HOURS=72 (docker-compose override; default en settings.py)
- INFLOW_THRESHOLD_USD=200000
- TELEGRAM_BOT_TOKEN=renovado en BotFather (override en docker-compose.yml — actualizar .env)
- TELEGRAM_CHAT_ID=6517856768 (@mi_crypto_agent_bot)
- Máx score teórico real ≈ 67.5 pts (sin Coinglass/derivados)

## Estado operativo (2026-05-15)
- Pipeline: Discovery → Monitor (~532 tokens/ciclo, ~534 snapshots, ~113s) → Detector → Scorer → Executor
- 20 trades paper abiertos (12 tokens únicos en mexc/bitget); LTC, XAUT, XRP, BNB, DOGE cerrarán por MAX_HOLD en ~23h
- Telegram: best-effort — si falla, loguea y continúa guardando en DB + marcando `alert_sent=True`
- 160 tokens de gran cap removidos del watchlist (LTC, XAUT, BNB, XRP, DOGE, SHIB...)
- Watchlist filtrada: $2M–$100M market cap, sin top-100 conocidos
- Alembic en 0005 (`anticipation_minutes` en trades); orchestrator rebuildeado para reconocer 0004/0005
- Migración 0002 reescrita con `ADD COLUMN IF NOT EXISTS` (antes crasheaba al reiniciar si la columna ya existía)
- Executor: monitor de posiciones cada 30s (no 5min); max hold 72h antes de SL; heartbeat Redis cada 30s
- Scorer heartbeat: Redis `scorer:heartbeat` cada vez que procesa token ≥ umbral (TTL 12min)
- Discovery corre al startup y a las 02:00 UTC (APScheduler); trigger manual vía Dashboard ("Forzar scan ahora") → publica en `channel:control:discovery:run`
- Orchestrator health checks corregidos: Discovery ventana 25h (no 10min), Detector usa `MAX(TokenCandidate.last_checked)` en lugar de `Alert.sent_at`
- Dashboard: tooltip al hover sobre score muestra breakdown por componente (Inflow / On-chain / Precio / Funding)
- Performance screen: muestra `avg_anticipation_minutes` (vs oldest alert) en lugar de horas; umbral ≥ 30 min

## Próximos pasos
- Esperar cierre de trades paper por MAX_HOLD (~23h) para que el Learner tenga datos completos
- Actualizar TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, ALERT_THRESHOLD y MAX_HOLD_HOURS en .env (actualmente solo en docker-compose)
- Holders ERC-20: aparecerán en alertas tras el próximo Discovery (02:00 UTC) para tokens con contrato Ethereum
- Coinglass API pública v2 DEPRECADA — sin señales de derivados hasta nueva fuente
- CCXT da funding/OI solo para contratos SWAP, no spot

## Knowns issues / limitaciones
- Coinglass devuelve HTTP 500 en todos los endpoints → lp_holder y cl_short = 0 pts siempre
- Sin derivados, máx score alcanzable ≈ 67.5 pts (inflow 40 + precio 20 + funding neutro 7.5)
- Etherscan solo cubre tokens ERC-20 en Ethereum; BEP-20/Solana/etc → holders N/D
- CoinGecko free tier se rate-limita (429) en discovery → algunas páginas se pierden
- Scorer: Telegram es best-effort desde sesión 2026-05-13; si falla, loguea y continúa guardando en DB + marcando `alert_sent=True`

## Schema DB
**token_candidates** — columnas añadidas post-init:
- `volume_24h_usd` — migración 0002
- `score_breakdown` TEXT JSON — migración 0003
- `contract_address` TEXT — migración 0004

**trades** — columnas añadidas post-init:
- `anticipation_minutes` FLOAT — migración 0005 (calculado al abrir: entry_time − MIN(alert.sent_at))

## Instrucción de mantenimiento
Al finalizar cada sesión de trabajo, actualizar este archivo 
con los cambios realizados y el próximo paso pendiente.
Al finalizar cada sesión actualiza el archivo bitacora.md.
