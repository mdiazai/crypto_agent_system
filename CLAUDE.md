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

## Configuración activa (2026-05-14)
- ALERT_THRESHOLD=60 (docker-compose override; .env tiene 62 — actualizar manualmente)
- INFLOW_THRESHOLD_USD=200000
- TELEGRAM_BOT_TOKEN=renovado en BotFather (override en docker-compose.yml — actualizar .env)
- TELEGRAM_CHAT_ID=6517856768 (@mi_crypto_agent_bot)
- Máx score teórico real ≈ 67.5 pts (sin Coinglass/derivados)

## Estado operativo (2026-05-14)
- Pipeline: Discovery → Monitor (~247 tokens/ciclo) → Detector → Scorer → Executor
- Telegram activo y verificado (message_id=2 enviado en prueba)
- 160 tokens de gran cap removidos del watchlist (LTC, XAUT, BNB, XRP, DOGE, SHIB...)
- Watchlist filtrada: $2M–$100M market cap, sin top-100 conocidos
- Alembic en 0004 (columnas score_breakdown + contract_address)
- Executor heartbeat: Redis `executor:heartbeat` cada 30s (TTL 120s)
- Scorer heartbeat: Redis `scorer:heartbeat` cada vez que procesa token ≥ umbral (TTL 12min)
- Discovery corre al startup y a las 02:00 UTC (APScheduler)

## Próximos pasos
- Esperar cierre de trades paper para activar ciclo completo del Learner
- Actualizar TELEGRAM_BOT_TOKEN y ALERT_THRESHOLD en .env (actualmente solo en docker-compose)
- Holders ERC-20: aparecerán en alertas tras el próximo Discovery (02:00 UTC) para tokens con contrato Ethereum
- Coinglass API pública v2 DEPRECADA — sin señales de derivados hasta nueva fuente
- CCXT da funding/OI solo para contratos SWAP, no spot

## Knowns issues / limitaciones
- Coinglass devuelve HTTP 500 en todos los endpoints → lp_holder y cl_short = 0 pts siempre
- Sin derivados, máx score alcanzable ≈ 67.5 pts (inflow 40 + precio 20 + funding neutro 7.5)
- Etherscan solo cubre tokens ERC-20 en Ethereum; BEP-20/Solana/etc → holders N/D
- CoinGecko free tier se rate-limita (429) en discovery → algunas páginas se pierden

## Schema DB (token_candidates)
Columnas relevantes añadidas post-init:
- `volume_24h_usd` — migración 0002
- `score_breakdown` TEXT JSON — migración 0003
- `contract_address` TEXT — migración 0004

## Instrucción de mantenimiento
Al finalizar cada sesión de trabajo, actualizar este archivo 
con los cambios realizados y el próximo paso pendiente.
Al finalizar cada sesión actualiza el archivo bitacora.md.
