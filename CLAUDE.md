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
- [x] Fase 14 — Holder concentration multi-chain: BSCScan (BEP-20) + Helius (Solana SPL)

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

## Configuración activa (2026-05-28)
- ALERT_THRESHOLD=55 (en .env del VPS — el compose ya NO tiene override)
- MAX_HOLD_HOURS=72 (en .env del VPS — el compose ya NO tiene override)
- PRICE_MAX_USD=100 (filtro en pre_screener — tokens >$100 excluidos)
- INFLOW_THRESHOLD_USD=200000
- TELEGRAM_BOT_TOKEN en .env del VPS (el compose ya NO tiene override)
- Máx score teórico real ≈ 67.5 pts (sin Coinglass/derivados)
- MORALIS_API_KEY: configurado en .env del VPS (JWT 324 chars, free tier ~40k CU/día)
- HELIUS_API_KEY: configurado en .env del VPS (Solana SPL holders)
- FUENTE ÚNICA DE VERDAD: .env del VPS para todas las variables de configuración
- CRÍTICO: .env del VPS debe tener line endings LF (no CRLF) — usar `sed -i 's/\r//'` si se copia desde Windows

## Estado operativo (2026-05-28)
- Sistema corriendo en VPS 24/7 con restart: unless-stopped en todos los servicios
- Pipeline: Discovery → Monitor → Detector → Scorer → Executor operativo
- Circuit breaker: inactivo
- Firewall UFW activo: puertos 22, 8001, 8080, 3000 abiertos
- Discovery: 2097 tokens escaneados, 203 pasan pre_screener (filtro precio >$100)
- Executor: monitor de posiciones cada 30s; max hold 72h; price fetch con fallback; capital check
- Scorer: heartbeat independiente cada 60s (TTL 180s); filtra EXCLUDED_SYMBOLS antes de alertar
- pre_screener: LARGE_CAP_BLACKLIST extendida + filtro price_max_usd=$100
- Claude Advisor: claude-sonnet-4-6
- Monitor: ~79 tokens activos, ciclo cada 5 min; holder_top10_pct leído de DB (no en ciclo)
- Holder concentration: job separado cada 6h (APScheduler en monitor_agent)
  - Moralis (EVM): top-10 % de supply via `/erc20/{addr}/owners` (free tier, 3 req simultáneos, 1s delay)
  - Helius (Solana SPL): `getTokenLargestAccounts` + `getTokenSupply`
  - job filtra tokens activos con chain IN ('evm', 'solana') y contract_address IS NOT NULL
  - Semáforo + delay en Moralis: `asyncio.Semaphore(3)` + `asyncio.sleep(1.0)` por request
  - Cache en memoria 6h: evita re-consultar Moralis entre jobs
  - backfill_contracts.py: script one-shot para poblar contract_address desde CoinGecko
- Migración 0006: columna `chain` en token_candidates (aplicada manualmente vía psql)
- 144 tokens con contract_address en DB (64 nuevos tras backfill 2026-05-28)
- Detector: no sobreescribe holder_concentration_pct con None (guard añadido 2026-05-27)

## Próximos pasos
- Correr backfill_contracts.py periódicamente cuando Discovery rote tokens activos
- Validar que el Learner procesa trades cerrados cuando se acumulen datos
- Fix pendiente: circuit breaker publica `{"_system_alert": True, ...}` en `channel:detector:scored_token` → ruido no crítico
- Coinglass API pública v2 DEPRECADA — sin señales de derivados hasta nueva fuente
- CCXT da funding/OI solo para contratos SWAP, no spot
- Considerar integrar backfill de contract_address en Discovery (automático para tokens nuevos)

## Knowns issues / limitaciones
- Coinglass devuelve HTTP 500 en todos los endpoints → lp_holder y cl_short = 0 pts siempre
- Sin derivados, máx score alcanzable ≈ 67.5 pts (inflow 40 + precio 20 + funding neutro 7.5)
- CoinGecko free tier se rate-limita (429) en discovery → algunas páginas se pierden
- Circuit breaker system alert: executor publica en `channel:detector:scored_token` → se recibe a sí mismo, falla parse como ScoredToken → warning `invalid_payload` (no crítico)
- Scorer: Telegram es best-effort; si falla, loguea y continúa guardando en DB + marcando `alert_sent=True`
- Migración 0006: no se aplica automáticamente (imagen orchestrator cacheada). Workaround: aplicar via psql manual + UPDATE alembic_version
- Migraciones futuras: siempre hacer `docker compose build orchestrator` antes de up para que las migraciones nuevas estén en la imagen
- MORALIS_API_KEY en .env del VPS: debe estar en LF (no CRLF) y en una sola línea sin espacios embebidos. Docker Compose trunca valores con \r o \n internos
- Tokens con chain='unknown' y address 0x válida: saltean Moralis (OnchainClient detecta 'unknown' como chain inválida). Fix pendiente: usar _detect_chain como fallback en get_holder_concentration
- ~20% de tokens activos sin contract_address (tokens no listados en CoinGecko). Sin holder data para estos

## Schema DB
**token_candidates** — columnas añadidas post-init:
- `volume_24h_usd` — migración 0002
- `score_breakdown` TEXT JSON — migración 0003
- `contract_address` TEXT — migración 0004
- `chain` VARCHAR(16) — migración 0006 ("evm" | "solana" | NULL)

**trades** — columnas añadidas post-init:
- `anticipation_minutes` FLOAT — migración 0005 (calculado al abrir: entry_time − MIN(alert.sent_at))

## Instrucción de mantenimiento
Al finalizar cada sesión de trabajo, actualizar este archivo 
con los cambios realizados y el próximo paso pendiente.
Al finalizar cada sesión actualiza el archivo bitacora.md.
