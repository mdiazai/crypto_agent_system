# MASTER PROMPT — Sistema Multi-Agente de Detección de Criminal Pumps
### Para usar directamente en Claude Code (VS Code / Terminal)

---

## ROL Y CONTEXTO

Eres un Arquitecto de Software Senior especializado en Trading Algorítmico, Sistemas Multi-Agente con IA, y Fintech. Tienes dominio experto en Python 3.11 con asyncio, FastAPI, CCXT, análisis on-chain, y arquitecturas de microservicios.

Vas a construir **desde cero** un sistema automatizado de detección y ejecución de "Criminal Pumps" en criptomonedas, estructurado como un sistema de **agentes autónomos orquestados**, inspirado en ingeniería inversa de un caso de éxito real. El sistema debe ser superior al original: más modular, más robusto, con mejor observabilidad y un ciclo de aprendizaje más sofisticado.

---

## STACK TECNOLÓGICO OBLIGATORIO

```
Lenguaje:       Python 3.11+ con asyncio
API Framework:  FastAPI
Cache/Queue:    Redis (pub/sub para coordinación entre agentes)
Base de Datos:  PostgreSQL (historial de trades y aprendizaje)
Exchange Lib:   CCXT (para MEXC y Bitget; diseñado para agregar más)
Alertas:        Telegram Bot API (python-telegram-bot)
On-Chain:       Glassnode API / Etherscan API / Solscan API
Observabilidad: Prometheus + Grafana (métricas) + Sentry (errores)
Scheduler:      APScheduler (AsyncIOScheduler)
LLM Orquestador: Anthropic Claude API (claude-sonnet-4-20250514)
Contenedores:   Docker + Docker Compose (para deploy en VPS)
CI/CD:          GitHub Actions (opcional, fase 2)
```

---

## ARQUITECTURA DEL SISTEMA — 7 AGENTES + ORQUESTADOR

El sistema se compone de los siguientes agentes autónomos, cada uno en su propio módulo de Python:

```
crypto_agent_system/
├── orchestrator/           # Orquestador central (Claude API)
├── agents/
│   ├── discovery/          # Agente 1: Escaneo diario de tokens
│   ├── monitor/            # Agente 2: Monitoreo cada 5 min
│   ├── detector/           # Agente 3: Lógica de detección (Long/Classic)
│   ├── scorer/             # Agente 4: Puntuación y alertas Telegram
│   ├── executor/           # Agente 5: Ejecución de trades (CCXT)
│   ├── learner/            # Agente 6: Ciclo de aprendizaje ML
│   └── dashboard/          # Agente 7: API FastAPI + WebSocket UI
├── shared/
│   ├── models/             # SQLAlchemy models (PostgreSQL)
│   ├── redis_bus/          # Message bus (Redis pub/sub)
│   ├── config/             # Config centralizada (.env)
│   └── utils/              # Helpers, logging, retry logic
├── tests/                  # Pytest (unit + integration)
├── docker/                 # Dockerfiles por servicio
├── docker-compose.yml
├── .env.example
└── requirements.txt
```

---

## INSTRUCCIONES DE CONSTRUCCIÓN — FASE POR FASE

### FASE 0 — SETUP INICIAL (Ejecutar primero)

**Tarea:** Genera la estructura completa de carpetas y archivos base del proyecto.

1. Crea toda la estructura de directorios indicada arriba.
2. Genera `requirements.txt` con todas las dependencias necesarias:
   - `ccxt`, `anthropic`, `fastapi`, `uvicorn`, `sqlalchemy`, `asyncpg`, `redis`, `apscheduler`, `python-telegram-bot`, `httpx`, `pydantic`, `python-dotenv`, `prometheus-client`, `sentry-sdk`, `pytest`, `pytest-asyncio`, `alembic`
3. Genera `.env.example` con todas las variables necesarias:
   - Claves API: `ANTHROPIC_API_KEY`, `MEXC_API_KEY`, `MEXC_SECRET`, `BITGET_API_KEY`, `BITGET_SECRET`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `GLASSNODE_API_KEY`, `ETHERSCAN_API_KEY`
   - Config DB: `DATABASE_URL`, `REDIS_URL`
   - Config sistema: `DISCOVERY_SCHEDULE_HOUR`, `MONITOR_INTERVAL_SECONDS=300`, `CAPITAL_TOTAL_USD`, `MEXC_ALLOCATION_PCT=69`, `BITGET_ALLOCATION_PCT=31`
4. Genera `docker-compose.yml` con servicios: `postgres`, `redis`, `orchestrator`, `discovery`, `monitor`, `detector`, `scorer`, `executor`, `learner`, `dashboard`, `prometheus`, `grafana`.
5. Genera `shared/config/settings.py` usando Pydantic `BaseSettings` que carga todas las variables del `.env`.

---

### FASE 1 — SHARED LAYER (Base de datos y message bus)

**Tarea:** Construye la capa compartida que todos los agentes usan.

#### 1A — Modelos PostgreSQL (`shared/models/`)

Crea con SQLAlchemy (async) los siguientes modelos:

```python
# Token candidato en watchlist
class TokenCandidate(Base):
    id, symbol, exchange, added_at, last_checked, status (active/removed)
    detection_score, pattern_type (long_pump/classic), holder_concentration_pct
    inflow_usd, alert_sent, notes

# Trade ejecutado
class Trade(Base):
    id, token_symbol, exchange, direction (buy/sell)
    entry_price, exit_price, quantity, capital_used_usd
    entry_time, exit_time, pnl_usd, pnl_pct
    pattern_detected, entry_quality (good/bad/early/late)  # para el learner
    score_at_entry

# Alerta Telegram enviada
class Alert(Base):
    id, token_symbol, score, pattern_type, sent_at, telegram_message_id

# Log del ciclo de aprendizaje
class LearningLog(Base):
    id, created_at, tokens_evaluated, accuracy_rate, 
    avg_entry_quality, weights_adjusted (JSON), notes
```

Genera también `alembic.ini` y la migración inicial.

#### 1B — Redis Message Bus (`shared/redis_bus/`)

Crea un sistema pub/sub con los siguientes canales:
- `channel:discovery:new_candidates` — Discovery publica nuevos tokens
- `channel:monitor:pump_signal` — Monitor publica señales detectadas
- `channel:detector:scored_token` — Detector publica token con score
- `channel:executor:trade_result` — Executor publica resultado del trade
- `channel:learner:feedback` — Learner publica ajustes de pesos

Implementa `RedisMessageBus` con métodos `publish(channel, payload)` y `subscribe(channel, callback)` usando `aioredis`.

---

### FASE 2 — AGENTE 1: DISCOVERY (`agents/discovery/`)

**Tarea:** Construye el agente que escanea tokens una vez al día.

**Lógica:**
1. Se ejecuta via APScheduler una vez al día a la hora configurada.
2. Llama a las APIs de CoinGecko y CoinMarketCap para obtener listado completo de tokens disponibles en MEXC y Bitget.
3. Para cada token aplica **filtro pre-screening** (criterios configurables):
   - Market cap mínimo / máximo (ej. $5M - $500M: zona de pumps)
   - Volumen 24h / market cap ratio > umbral
   - Antigüedad del token < X días (tokens nuevos son más vulnerables)
   - No estar en blacklist de tokens ya analizados y descartados
4. Los tokens que pasan el filtro se guardan/actualizan en `TokenCandidate` con status `active`.
5. Los tokens previamente activos que ya NO pasan el filtro se marcan como `removed`.
6. Publica la lista actualizada en `channel:discovery:new_candidates`.
7. Loguea estadísticas en Prometheus: `discovery_tokens_scanned`, `discovery_candidates_found`, `discovery_candidates_removed`.

**Implementar:**
- `discovery_agent.py` con clase `DiscoveryAgent`
- `exchange_scanner.py` con integración a APIs de exchanges vía CCXT y CoinGecko
- `pre_screener.py` con la lógica de filtro configurable
- `Dockerfile` para el servicio

---

### FASE 3 — AGENTE 2: MONITOR (`agents/monitor/`)

**Tarea:** Construye el agente que monitorea tokens pre-seleccionados cada 5 minutos.

**Lógica:**
1. Se ejecuta vía APScheduler cada 300 segundos (configurable).
2. Lee todos los `TokenCandidate` con status `active` desde PostgreSQL.
3. Para cada token activo, obtiene en paralelo (asyncio.gather):
   - Precio actual y orderbook (via CCXT WebSocket o REST)
   - Datos on-chain vía Etherscan/Solscan: flujo de wallets hacia exchanges (inflow)
   - Datos de holders: concentración (via Glassnode o scraping on-chain)
4. Estructura un `TokenSnapshot` con todos los datos frescos.
5. Publica cada snapshot en `channel:monitor:pump_signal` para que el Detector lo procese.
6. Maneja rate limits de APIs con retry exponential backoff.
7. Loguea en Prometheus: `monitor_tokens_checked`, `monitor_api_errors`, `monitor_cycle_duration_seconds`.

**Implementar:**
- `monitor_agent.py` con clase `MonitorAgent`
- `data_fetcher.py` con fetchers paralelos (price, onchain, holders)
- `onchain_client.py` para Etherscan + Glassnode APIs
- `Dockerfile`

---

### FASE 4 — AGENTE 3: DETECTOR (`agents/detector/`)

**Tarea:** Construye el agente de detección de patrones con lógica heurística.

**Lógica de Detección (implementar ambos patrones):**

**Patrón A — Long Pump:**
- Inflow masivo hacia exchange en las últimas 1-4 horas (> umbral configurable en USD)
- Holder concentration aumentando (top 10 wallets > 60% del supply)
- Volumen creciente con precio estable (acumulación silenciosa)
- Short interest bajo (poco shorting = sin resistencia)

**Patrón B — Classic (Short Squeeze):**
- Alto short interest en el token (> 20% del float)
- Funding rate negativo persistente (futuros perpetuos)
- Inflow masivo simultáneo (squeeze activator)
- Holder concentration en manos fuertes (no panic sellers)

**Para cada TokenSnapshot recibido del Monitor:**
1. Evalúa qué patrón está "sonando más fuerte" (score 0-100 para cada patrón).
2. Calcula `composite_score` = max(long_pump_score, classic_score) ponderado por historial del Learner.
3. Si `composite_score >= ALERT_THRESHOLD` (default: 70), marca el token para alerta.
4. Publica en `channel:detector:scored_token` con el score, patrón dominante y métricas.
5. **INTEGRACIÓN CON CLAUDE API:** Para tokens con score >= 85, hacer una llamada adicional a `claude-sonnet-4-20250514` con el snapshot completo del token para validación contextual y generación de un resumen en lenguaje natural del por qué es una oportunidad. Incluir este análisis en la alerta Telegram.

**Implementar:**
- `detector_agent.py` con clase `DetectorAgent`
- `pattern_long_pump.py` con la lógica del patrón A
- `pattern_classic_squeeze.py` con la lógica del patrón B
- `score_engine.py` que combina ambos patrones con pesos ajustables
- `claude_validator.py` para la validación con LLM en casos de alto score
- `Dockerfile`

---

### FASE 5 — AGENTE 4: SCORER & ALERTER (`agents/scorer/`)

**Tarea:** Construye el agente de alertas via Telegram.

**Lógica:**
1. Escucha `channel:detector:scored_token`.
2. Para cada token puntuado con score >= umbral:
   - Formatea un mensaje rico para Telegram con: ticker, score (con emoji de intensidad 🔴🟠🟡), patrón detectado, precio actual, inflow estimado en USD, concentración de holders en %, análisis del LLM (si aplica), y botones inline para "Ver Chart" y "Ejecutar Trade".
3. Envía el mensaje via python-telegram-bot al `TELEGRAM_CHAT_ID` configurado.
4. Guarda la alerta en la tabla `Alert` de PostgreSQL.
5. Implementa deduplicación: no enviar segunda alerta del mismo token si ya se envió en las últimas 2 horas.

**Formato del mensaje Telegram:**
```
🚨 PUMP SIGNAL DETECTADO
━━━━━━━━━━━━━━━━━
🪙 Token: $SYMBOL
📊 Score: 87/100 🔴
🎯 Patrón: Long Pump
💰 Precio: $0.0284
📥 Inflow: +$2.4M (últimas 2h)
👥 Holders TOP10: 71% del supply
━━━━━━━━━━━━━━━━━
🤖 Análisis IA: [texto del LLM]
⏰ Detectado: 09:34 UTC
[📈 Ver Chart] [⚡ Ejecutar]
```

**Implementar:**
- `scorer_agent.py` con clase `ScorerAgent`
- `telegram_client.py` con la integración completa de Telegram Bot API
- `message_formatter.py` con templates de mensajes
- `Dockerfile`

---

### FASE 6 — AGENTE 5: EXECUTOR (`agents/executor/`)

**Tarea:** Construye el agente de ejecución de trades completamente autónomo.

**Lógica:**
1. Escucha `channel:detector:scored_token` (y opcionalmente comandos del dashboard).
2. Calcula el capital a usar: `CAPITAL_TOTAL_USD * allocation_pct` por exchange.
3. Para MEXC: ejecuta market buy del porcentaje configurado (`MEXC_ALLOCATION_PCT`).
4. Para Bitget: ejecuta market buy del porcentaje configurado (`BITGET_ALLOCATION_PCT`).
5. Implementa **gestión de riesgo** (CRÍTICO):
   - Stop loss automático: si el precio cae > `STOP_LOSS_PCT` (default: 8%) desde entrada, vende todo.
   - Take profit escalonado: vende 50% al llegar a +30%, 30% al llegar a +60%, 20% restante al +100% o stop.
   - Maximum drawdown diario: si las pérdidas del día superan `MAX_DAILY_LOSS_PCT` (default: 15%), suspender ejecución automática y alertar via Telegram.
   - Circuit breaker: si hay 3 trades perdedores consecutivos, pausar 24h y alertar.
6. Registra cada trade en la tabla `Trade` de PostgreSQL.
7. Publica resultado en `channel:executor:trade_result`.
8. **MODO PAPER TRADING**: Si `PAPER_TRADING=true` en .env, simula los trades sin ejecutar órdenes reales (para testing).

**Implementar:**
- `executor_agent.py` con clase `ExecutorAgent`
- `exchange_client.py` con CCXT para MEXC y Bitget (ejecución asíncrona)
- `risk_manager.py` con stop loss, take profit, circuit breakers
- `position_tracker.py` que monitorea posiciones abiertas
- `Dockerfile`

---

### FASE 7 — AGENTE 6: LEARNER (`agents/learner/`)

**Tarea:** Construye el ciclo de aprendizaje automático.

**Lógica:**
1. Se ejecuta cada 24 horas (o bajo demanda via API).
2. Lee los últimos `N` trades completados desde PostgreSQL.
3. Para cada trade, evalúa `entry_quality`:
   - `perfect`: El precio subió > 20% en las primeras 4h después de la entrada
   - `good`: El precio subió > 10% en 12h
   - `early`: El precio subió pero después de > 6h de la entrada
   - `late`: El precio ya había subido > 15% en el momento de entrada
   - `bad`: El trade fue stop-lossed o resultó en pérdida
4. Calcula métricas agregadas: win_rate, avg_pnl, avg_entry_quality_score.
5. Ajusta los **pesos** del score engine en el Detector basado en qué métricas correlacionaron mejor con los `perfect` y `good` trades:
   - Si los mejores trades tenían inflow > $X → aumentar peso del inflow
   - Si holder_concentration > Y correlaciona con buenos trades → aumentar ese peso
   - Usa una regresión logística simple o un modelo XGBoost entrenado on-line
6. Persiste los nuevos pesos en PostgreSQL (tabla `LearningLog`) y los publica via Redis para que el Detector los tome.
7. Envía reporte semanal via Telegram con métricas clave.

**Implementar:**
- `learner_agent.py` con clase `LearnerAgent`
- `trade_evaluator.py` que clasifica la calidad de cada entrada
- `weight_optimizer.py` con el modelo de ML (scikit-learn: LogisticRegression o XGBoost)
- `metrics_reporter.py` para el reporte Telegram semanal
- `Dockerfile`

---

### FASE 8 — AGENTE 7: DASHBOARD (`agents/dashboard/`)

**Tarea:** Construye la API REST + WebSocket dashboard de control.

**Endpoints FastAPI a implementar:**

```python
# Autenticación
POST /auth/login           # JWT token
POST /auth/refresh

# Tokens en watchlist
GET  /tokens               # Lista de candidatos activos con scores
GET  /tokens/{symbol}      # Detalle: chart data, métricas, historial

# Trades
GET  /trades               # Historial de trades
GET  /trades/summary       # P&L total, win rate, etc.

# Configuración del sistema
GET  /config               # Configuración actual
PUT  /config               # Actualizar: capital, % exchanges, umbrales

# Control de agentes
POST /agents/discovery/run      # Forzar ejecución del Discovery
POST /agents/monitor/run        # Forzar ciclo de monitoreo
POST /agents/learner/evaluate   # Forzar ciclo de aprendizaje

# Ejecución manual
POST /trades/execute        # Ejecutar trade manual con {symbol, direction, capital}
POST /trades/{id}/close     # Cerrar posición manualmente

# WebSocket
WS   /ws/signals            # Stream en tiempo real de señales detectadas
WS   /ws/trades             # Stream de ejecuciones
```

Implementar también:
- Autenticación JWT con `python-jose`
- Rate limiting con `slowapi`
- CORS configurado para el frontend
- Documentación automática en `/docs`

**Implementar:**
- `dashboard_agent.py` con la app FastAPI
- `routers/` con los routers organizados por dominio
- `auth/` con JWT middleware
- `websocket_manager.py` para los streams en tiempo real
- `Dockerfile`

---

### FASE 9 — ORQUESTADOR CENTRAL (`orchestrator/`)

**Tarea:** Construye el orquestador que coordina todos los agentes.

El orquestador usa la **Claude API** como cerebro de coordinación:

1. Es el punto de entrada del sistema al arrancar.
2. Inicializa todos los agentes en orden correcto.
3. Monitorea la salud de cada agente cada 60 segundos (health checks via Redis).
4. Si un agente falla, lo reinicia automáticamente (hasta 3 intentos).
5. Expone un endpoint `/health` que reporta el estado de todos los agentes.
6. **Modo Inteligente:** Cuando el sistema detecta condiciones de mercado anómalas (alta volatilidad, muchas señales simultáneas, etc.), llama a Claude API con el contexto completo del mercado para obtener una recomendación sobre si ajustar los umbrales temporalmente.

**Implementar:**
- `main.py` — entry point que levanta todos los servicios
- `agent_supervisor.py` — supervisor con health checks y restart logic
- `market_context.py` — análisis macro de condiciones de mercado
- `claude_advisor.py` — integración Claude API para decisiones de alto nivel
- `Dockerfile`

---

### FASE 10 — TESTS Y DOCUMENTACIÓN

**Tarea:** Genera el suite de tests y documentación.

1. **Tests unitarios** en `tests/unit/`:
   - `test_pattern_long_pump.py` — tests con datos mock
   - `test_pattern_classic.py`
   - `test_score_engine.py`
   - `test_risk_manager.py`
   - `test_trade_evaluator.py`

2. **Tests de integración** en `tests/integration/`:
   - `test_discovery_to_monitor.py` — flujo completo Discovery → Monitor
   - `test_monitor_to_executor.py` — flujo Monitor → Detector → Executor (con CCXT en modo testnet)

3. **README.md** completo con:
   - Descripción del sistema
   - Diagrama de arquitectura (Mermaid)
   - Guía de instalación paso a paso (Windows 11 y Linux VPS)
   - Variables de entorno documentadas
   - Guía de uso del Dashboard
   - Cómo agregar un nuevo exchange
   - Cómo interpretar las métricas del Learner

---

## REGLAS GLOBALES DE DESARROLLO

1. **Todo el código debe ser async** — usa `asyncio`, `aiohttp`, `asyncpg`, `aioredis`.
2. **Nunca hardcodear credenciales** — siempre desde variables de entorno via `settings.py`.
3. **Logging estructurado** — usa `structlog` con nivel configurable por agente.
4. **Manejo de errores robusto** — cada agente debe capturar excepciones, loguear en Sentry, y continuar sin caerse.
5. **Retry con backoff exponencial** — para todas las llamadas a APIs externas (ccxt, on-chain, Telegram).
6. **Rate limiting respetado** — maneja los límites de cada API según su documentación.
7. **Paper trading primero** — el flag `PAPER_TRADING=true` debe deshabilitar cualquier ejecución real.
8. **Principio de responsabilidad única** — cada agente hace una cosa y la hace bien.
9. **Sin dependencias circulares** — los agentes se comunican solo via Redis pub/sub o REST.
10. **Type hints en todo el código** — usa `typing` y `pydantic` para validación de datos.

---

## INSTRUCCIÓN DE INICIO PARA CLAUDE CODE

**Comienza por la FASE 0.** Genera la estructura de carpetas completa y todos los archivos base antes de avanzar a la siguiente fase. Después de cada fase, confirma que el código es correcto y funcional antes de continuar. Si necesitas tomar decisiones de diseño no especificadas, elige la opción más robusta y documentala en un comentario inline.

**Primera instrucción:** `"Empieza por la FASE 0: genera la estructura de carpetas completa del proyecto crypto_agent_system, el requirements.txt, el .env.example, y el docker-compose.yml."`
