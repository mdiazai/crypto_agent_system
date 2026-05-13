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
- Pipeline completo funcionando: Discovery → Monitor(534 tokens/ciclo) → Detector → Executor
- 4 trades paper abiertos: ACN x2, LAB x2 (entrada ~00:37 UTC del 2026-05-13)
- Top score actual: UMXM 54, GOLD(PAXG) 50, EUR 48 — todos bajo umbral de 62
- Discovery corre al startup y cada día a las 02:00 UTC (APScheduler cron)
- Alembic stamped en 0002 (columna volume_24h_usd ya existía en DB)

## Próximo paso
- Esperar cierre de los 4 trades paper (LAB, ACN) para activar Learner
- Revisar aprendizaje del Learner tras primer ciclo de trades
- Monitorear si algún token supera score 62 en próximos ciclos
- Performance UI: http://localhost:8001/static/performance.html (link en nav del dashboard)
- On-chain: Coinglass (sin key), Etherscan (key gratuita), CryptoQuant (key gratuita)
- ALERT_THRESHOLD=62 (bajado de 70; máx teórico sin Glassnode = 93 pts)

## Fixes sesión 2026-05-13
- Discovery: ahora suscribe a channel:control:discovery:run → botón "Forzar scan" funciona
- Orchestrator health: Detector usa last_checked (no Alert.sent_at) → muestra healthy correctamente
- Orchestrator health: Discovery usa ventana 25h (era 10min → always unhealthy)
- Orchestrator health: mensajes "sin datos en DB" → mensajes descriptivos por agente
- Dashboard: auto-refresh 30s → 60s; botón "Forzar scan ahora" en card de Discovery
- Dashboard: counter de tokens monitoreados en card de Monitor
- Alembic 0002: reescrito con ADD COLUMN IF NOT EXISTS para evitar crash en restart
## Instrucción de mantenimiento
Al finalizar cada sesión de trabajo, actualizar este archivo 
con los cambios realizados y el próximo paso pendiente. Al finalizar cada sesión actualiza el archivo bitacora.md con lo hecho nuevo sobre el proyecto en esta.