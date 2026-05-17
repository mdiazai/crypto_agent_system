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

## Estado del deploy (VPS Hostinger — activo desde 2026-05-17)
- VPS: 167.88.33.68 — Ubuntu 24.04, 8GB RAM, 2 cores, 100GB SSD
- Deploy: `/opt/crypto_agent_system`
- Dashboard UI: http://167.88.33.68:8001 (admin / ver .env DASHBOARD_PASSWORD)
- Orchestrator:  http://167.88.33.68:8080/health
- Grafana:       http://167.88.33.68:3000 (admin / admin)
- SSH:           ssh root@167.88.33.68
- Instancia local: APAGADA (docker compose down ejecutado 2026-05-17)

## Configuración activa (2026-05-17)
- ALERT_THRESHOLD=60 (sincronizado en .env del VPS)
- MAX_HOLD_HOURS=72 (agregado al .env del VPS)
- INFLOW_THRESHOLD_USD=200000
- TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID=6517856768 en .env del VPS
- Máx score teórico real ≈ 67.5 pts (sin Coinglass/derivados)

## Estado operativo (2026-05-17)
- Sistema corriendo en VPS 24/7 con restart: unless-stopped en todos los servicios
- DB nueva en VPS — sin historial de trades previos (los trades del sistema local no se migraron)
- Pipeline: Discovery → Monitor → Detector → Scorer → Executor operativo
- Circuit breaker: inactivo
- Firewall UFW activo: puertos 22, 8001, 8080, 3000 abiertos
- Discovery corre al startup y a las 02:00 UTC; primer scan completado: 2099 tokens, 589 pasaron pre_screener
- Executor: monitor de posiciones cada 30s; max hold 72h; price fetch con fallback; capital check
- Scorer: filtra EXCLUDED_SYMBOLS antes de enviar alerta
- pre_screener: LARGE_CAP_BLACKLIST completa (large-caps + stablecoins)
- Claude Advisor: claude-sonnet-4-6

## Próximos pasos
- Monitorear primeras señales reales en el VPS (scorer y learner en "unknown" hasta primer trade)
- Validar que Telegram envía alertas correctamente desde el VPS
- Validar que el Learner procesa trades cerrados cuando se acumulen datos
- Fix pendiente: circuit breaker publica `{"_system_alert": True, ...}` en `channel:detector:scored_token` → ruido no crítico
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
