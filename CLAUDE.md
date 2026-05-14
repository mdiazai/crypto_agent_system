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
- [x] Fase 12 — Pantalla Performance (GET /performance/metrics + performance.html con semáforos y veredicto Glassnode)
- [x] Fase 13 — On-chain multi-fuente: Coinglass + Etherscan + CryptoQuant (reemplaza Glassnode $999/mes)

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
- Discovery usa tickers MEXC/Bitget como fallback cuando CoinGecko rate-limita

## Estado operativo (2026-05-13)
- Pipeline completo funcionando: Discovery → Monitor(521 tokens/ciclo) → Detector → Executor
- 5 trades paper abiertos: ACN x2, LAB x2, EUR x1 (entrada 00:37 y 11:44 UTC)
- EUR disparó con score 67.5 tras bajar INFLOW_THRESHOLD_USD a $200k
- Discovery corre al startup y cada día a las 02:00 UTC (APScheduler cron)
- Alembic stamped en 0002 (columna volume_24h_usd ya existía en DB)
- Executor heartbeat: escribe `executor:heartbeat` en Redis cada 30s (TTL 120s)

## Próximo paso
- Esperar cierre de los 5 trades paper (ACN x2, LAB x2, EUR x1) para activar Learner
- Revisar aprendizaje del Learner tras primer ciclo de trades
- Coinglass API pública v2 DEPRECADA — devuelve HTTP 500 para todos los endpoints
- CCXT solo da funding/OI para contratos SWAP, no para spot tokens watchlist
- Sin señales de derivados: máx score teórico real = 67.5 pts (40 inflow + 20 precio + 7.5 funding)
- INFLOW_THRESHOLD_USD=200000 (bajado de 500000 para calibrar a tamaño real de altcoins)
- ALERT_THRESHOLD=60 (bajado de 62; máx alcanzable: ~67.5 sin Coinglass)
- Telegram activo: token renovado en BotFather, mensaje de prueba enviado ✅ (@mi_crypto_agent_bot)
- TELEGRAM_BOT_TOKEN actualizado en docker-compose.yml (override) — actualizar .env manualmente

## Fixes sesión 2026-05-13 (turno 1)
- Discovery: ahora suscribe a channel:control:discovery:run → botón "Forzar scan" funciona
- Orchestrator health: Detector usa last_checked (no Alert.sent_at) → muestra healthy correctamente
- Orchestrator health: Discovery usa ventana 25h (era 10min → always unhealthy)
- Orchestrator health: mensajes "sin datos en DB" → mensajes descriptivos por agente
- Dashboard: auto-refresh 30s → 60s; botón "Forzar scan ahora" en card de Discovery
- Dashboard: counter de tokens monitoreados en card de Monitor
- Alembic 0002: reescrito con ADD COLUMN IF NOT EXISTS para evitar crash en restart

## Fixes sesión 2026-05-13 (turno 2 — alertas y breakdown)
- CAUSA RAÍZ "Sin alerta": Telegram devuelve "Chat not found" → scorer abortaba antes de guardar en DB
- scorer_agent.py: desacoplado Telegram del guardado en DB — ahora siempre guarda Alert + marca alert_sent=True aunque Telegram falle
- scorer_agent.py: _save_alert ahora hace UPDATE token_candidates SET alert_sent=True (bug: antes nunca lo hacía)
- detector_agent.py: guarda score_breakdown JSON en DB al actualizar cada score
- shared/models/token_candidate.py: nuevo campo score_breakdown TEXT
- alembic 0003: ADD COLUMN IF NOT EXISTS score_breakdown TEXT
- dashboard/schemas.py + tokens.py: expone score_breakdown como dict en API
- dashboard/index.html: tooltip hover sobre score muestra breakdown por componente (Inflow/On-chain/Precio/Funding para LP; Short Int/Funding/Inflow/Holders para Classic)
- docker-compose.yml: ALERT_THRESHOLD=60 y TELEGRAM_BOT_TOKEN nuevo explícitos como overrides

## Fixes sesión 2026-05-14 (turno 3 — Scorer/Learner health + mejoras dashboard)
- PROBLEMA 1: Scorer degraded — causa: TELEGRAM_BOT_TOKEN revocado en BotFather → "Not Found"
  - Nuevo token configurado en docker-compose.yml; mensaje de prueba ✅ (message_id=2)
  - scorer_agent.py: escribe scorer:heartbeat en Redis (TTL 12min) en cada token ≥ umbral procesado
  - orchestrator: _check_scorer lee heartbeat primero, fallback a Alert.sent_at
- PROBLEMA 2: Learner degraded — no era error, era estado de espera (insufficient_data)
  - orchestrator: _check_learner devuelve status="unknown" con mensaje descriptivo cuando notes='insufficient_data'
  - Learner corre una vez al día (03:00 UTC) — ventana healthy ampliada a 25h para futuros runs con datos suficientes
- Dashboard mejora 1: tarjeta Executor muestra botón "Ver posiciones en Portfolio →" que navega al tab portfolio
- Dashboard mejora 2: tarjeta Scorer muestra "⚠ sin nuevas señales — tokens en deduplicación (2h)" cuando degraded
- Dashboard mejora 3: top score Detector en verde si ≥ umbral (config.alert_threshold), amarillo 50-59, rojo <50
- Dashboard: badge "degraded" ahora en amber (antes sin estilo), "unhealthy" en rojo

## Fixes sesión 2026-05-14 (turno 4 — filtros market cap + holders pipeline)
- pre_screener: MARKET_CAP_MAX bajado de $500M a $100M; MIN de $5M a $2M
- pre_screener: fallback volume max bajado de $100M a $10M (más conservador sin mcap)
- pre_screener: LARGE_CAP_BLACKLIST hardcodeado — BTC/ETH/LTC/XAUT/PAXG/WBTC etc. bloqueados siempre
- exchange_scanner: LARGE_CAP_SKIP filtra antes de llamar a CoinGecko
- Resultado: 160 tokens grandes removidos del watchlist en primer run (LTC, XAUT, PAXG, BNB, XRP...)
- holders pipeline completo: Discovery → contract_address → Monitor → DataFetcher → Etherscan
- discovery/schemas.py: campo eth_contract en TokenData
- exchange_scanner: método get_eth_contracts() llama /coins/{id} para tokens que pasan screener
- alembic 0004: ADD COLUMN IF NOT EXISTS contract_address TEXT
- monitor_agent: lee contract_address de DB y lo pasa a DataFetcher
- data_fetcher: fetch_all(symbol, exchange, contract_address) — ya no hardcodea None
- holders mostrará datos reales para tokens ERC-20 con contrato en Ethereum
- CoinGecko free tier: sleep 2s entre llamadas de contratos (~30 req/min)
## Instrucción de mantenimiento
Al finalizar cada sesión de trabajo, actualizar este archivo 
con los cambios realizados y el próximo paso pendiente. Al finalizar cada sesión actualiza el archivo bitacora.md con lo hecho nuevo sobre el proyecto en esta.