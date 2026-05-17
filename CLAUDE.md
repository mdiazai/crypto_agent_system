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

## Configuración activa (2026-05-16 turno 2)
- ALERT_THRESHOLD=60 (docker-compose override; .env tiene 62 — actualizar manualmente)
- MAX_HOLD_HOURS=72 (docker-compose override; default en settings.py)
- INFLOW_THRESHOLD_USD=200000
- TELEGRAM_BOT_TOKEN=renovado en BotFather (override en docker-compose.yml — actualizar .env)
- TELEGRAM_CHAT_ID=6517856768 (@mi_crypto_agent_bot)
- Máx score teórico real ≈ 67.5 pts (sin Coinglass/derivados)

## Estado operativo (2026-05-16 turno 3)
- Pipeline: Discovery → Monitor (~532 tokens/ciclo, ~534 snapshots, ~113s) → Detector → Scorer → Executor
- 1 posición paper abierta: GOLD(PAXG)/mexc (~39h open, PnL -0.68%, cierra por MAX_HOLD en ~33h)
- Circuit breaker: RESETEADO MANUALMENTE (pérdidas vinieron de tokens large-cap incorrectos, no del algoritmo)
- Watchlist confirmada limpia: 0 large-caps activos en token_candidates tras el rebuild de discovery
- Telegram: best-effort — si falla, loguea y continúa guardando en DB + marcando `alert_sent=True`
- Watchlist filtrada: $2M–$100M market cap, sin top-100 conocidos + stablecoins
- Alembic en 0005 (`anticipation_minutes` en trades); orchestrator rebuildeado para reconocer 0004/0005
- Executor: monitor de posiciones cada 30s; max hold 72h; price fetch con fallback a exchange alternativo; capital check (bloquea si < 10% capital disponible)
- Scorer: filtra `EXCLUDED_SYMBOLS` (espejo de `LARGE_CAP_BLACKLIST`) antes de enviar alerta
- pre_screener: `LARGE_CAP_BLACKLIST` extendida con TRX, SHIB, TON, GOLD, SILVER, SUI, APT, INJ, stablecoins
- Scorer heartbeat: Redis `scorer:heartbeat` (TTL 12min)
- Discovery corre al startup y a las 02:00 UTC (APScheduler); trigger manual vía Dashboard
- Performance screen: muestra `avg_anticipation_minutes` (vs oldest alert)
- Claude Advisor operativo con `claude-sonnet-4-6` (corregido desde `claude-sonnet-4-20250514` deprecado)

## Próximos pasos
- Esperar cierre de GOLD(PAXG) por MAX_HOLD (~33h) — única posición abierta, PnL -0.68%
- Validar que el Learner procesa trades cerrados una vez que se acumulen datos completos
- Monitorear el próximo ciclo de Discovery (02:00 UTC) para confirmar que no entran large-caps
- Actualizar TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, ALERT_THRESHOLD y MAX_HOLD_HOURS en .env (actualmente solo en docker-compose)
- Fix pendiente: circuit breaker publica `{"_system_alert": True, ...}` en `channel:detector:scored_token` → executor lo recibe y loguea `invalid_payload` (ruido, no crítico)
- Coinglass API pública v2 DEPRECADA — sin señales de derivados hasta nueva fuente
- CCXT da funding/OI solo para contratos SWAP, no spot

## Knowns issues / limitaciones
- Coinglass devuelve HTTP 500 en todos los endpoints → lp_holder y cl_short = 0 pts siempre
- Sin derivados, máx score alcanzable ≈ 67.5 pts (inflow 40 + precio 20 + funding neutro 7.5)
- Etherscan solo cubre tokens ERC-20 en Ethereum; BEP-20/Solana/etc → holders N/D
- CoinGecko free tier se rate-limita (429) en discovery → algunas páginas se pierden
- Circuit breaker system alert: executor publica en `channel:detector:scored_token` → se recibe a sí mismo, falla parse como ScoredToken → warning `invalid_payload` (no crítico)
- Scorer: Telegram es best-effort; si falla, loguea y continúa guardando en DB + marcando `alert_sent=True`

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
