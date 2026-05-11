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

## Próximo paso
- Observar ciclos de Monitor/Detector sobre los 532 candidatos detectados
- Cuando un token supere score 70+, el Scorer enviará alerta por Telegram
- Revisar aprendizaje del Learner tras los primeros trades paper
- Performance UI: http://localhost:8001/static/performance.html (link en nav del dashboard)
- On-chain: Coinglass (sin key), Etherscan (key gratuita), CryptoQuant (key gratuita)
- ALERT_THRESHOLD=62 (bajado de 70; máx teórico sin Glassnode = 93 pts)
## Instrucción de mantenimiento
Al finalizar cada sesión de trabajo, actualizar este archivo 
con los cambios realizados y el próximo paso pendiente.