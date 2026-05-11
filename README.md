# Crypto Agent System — Criminal Pump Detector

[![GitHub](https://img.shields.io/badge/GitHub-mdiazai%2Fcrypto__agent__system-181717?logo=github)](https://github.com/mdiazai/crypto_agent_system)

Sistema multi-agente de trading automatizado basado en el caso real del canal **KManuS88**, que transformó **$640 → $1,752** en 60-80 días detectando patrones de "Criminal Pump" en altcoins de baja capitalización.

---

## Arquitectura del Sistema

```mermaid
flowchart TD
    CG[CoinGecko API] --> DA
    CCXT[CCXT / MEXC + Bitget] --> DA
    DA[Discovery Agent<br/>Scan cada 6h] -->|channel:discovery:new_candidates| MA

    MA[Monitor Agent<br/>Poll cada 5min] -->|channel:monitor:pump_signal| DET
    GN[Glassnode API] --> MA

    DET[Detector Agent<br/>Score Engine] -->|channel:detector:scored_token| SC
    CLAUDE[Claude API<br/>Validación] --> DET

    SC[Scorer Agent<br/>Alerter] -->|Telegram HTML| TG[Telegram Bot]
    SC -->|channel:detector:scored_token| EX

    EX[Executor Agent<br/>Paper / Real] -->|channel:executor:trade_result| LR
    EX --> DB[(PostgreSQL)]

    LR[Learner Agent<br/>XGBoost + Métricas] -->|WeightUpdate Redis| DET
    LR --> DB

    ORC[Orchestrator<br/>Supervisor + Claude Advisor] --> DB
    ORC --> TG

    DASH[Dashboard<br/>FastAPI + WebSocket] --> DB
    DASH -->|REST API| USER[Usuario / Frontend]

    REDIS[(Redis<br/>Pub/Sub + Config)] --- DA & MA & DET & SC & EX & LR & ORC & DASH
```

### Flujo de datos principal

```
TokenData (Discovery)
  → TokenSnapshot (Monitor)
    → ScoredToken (Detector, score 0-100)
      → Alert Telegram (Scorer)
      → PositionState (Executor, paper o real)
        → TradeResult (Executor)
          → LearningLog + WeightUpdate (Learner)
```

---

## Agentes

| Agente | Puerto Métricas | Descripción |
|---|---|---|
| Discovery | 9100 | Escanea MEXC + Bitget cada 6h, filtra por market cap y volumen |
| Monitor | 9101 | Recolecta precios, on-chain data y funding rates cada 5min |
| Detector | 9102 | Calcula score 0-100 para Long Pump y Classic Squeeze |
| Scorer | 9103 | Formatea y envía alertas Telegram, deduplicación 2h |
| Executor | 9104 | Abre/cierra posiciones con stop loss y take profit escalonado |
| Learner | 9105 | Evalúa trades, optimiza pesos con XGBoost, reporte semanal |
| Dashboard | 8001 | API REST + WebSocket, JWT auth, 16 endpoints |
| Orchestrator | 8080 | Health checks, Claude market advisor, migraciones Alembic |

---

## Instalación

### Requisitos previos

- Docker Desktop 4.x+
- Git
- API keys: Anthropic, MEXC, Bitget, Telegram Bot, Glassnode, CoinGecko

---

### Windows 11

```powershell
# 1. Clonar el repositorio
git clone <repo-url> C:\crypto_agent_system
cd C:\crypto_agent_system

# 2. Copiar variables de entorno
Copy-Item .env.example .env

# 3. Editar .env con tus API keys
notepad .env

# 4. Levantar todos los servicios
docker compose up -d

# 5. Verificar que todo está corriendo
docker compose ps

# 6. Ver logs del orchestrator (incluye migraciones)
docker compose logs -f orchestrator
```

> **Nota**: Docker Desktop debe tener el motor WSL2 habilitado (Settings → General → "Use the WSL 2 based engine").

---

### Linux VPS (Ubuntu 22.04+)

```bash
# 1. Instalar Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# 2. Clonar el repositorio
git clone <repo-url> ~/crypto_agent_system
cd ~/crypto_agent_system

# 3. Configurar variables de entorno
cp .env.example .env
nano .env

# 4. Levantar el sistema
docker compose up -d

# 5. Verificar servicios
docker compose ps

# 6. Ver logs en tiempo real
docker compose logs -f

# 7. (Opcional) Configurar reinicio automático al boot
sudo systemctl enable docker
```

---

## Variables de Entorno

Copia `.env.example` a `.env` y completa todas las variables marcadas como requeridas.

### API Keys

| Variable | Requerida | Descripción |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | Claude API key (console.anthropic.com) |
| `MEXC_API_KEY` | ✅ | MEXC exchange API key |
| `MEXC_SECRET_KEY` | ✅ | MEXC exchange secret |
| `BITGET_API_KEY` | ✅ | Bitget exchange API key |
| `BITGET_SECRET_KEY` | ✅ | Bitget exchange secret |
| `BITGET_PASSPHRASE` | ✅ | Bitget API passphrase |
| `TELEGRAM_BOT_TOKEN` | ✅ | Token del bot (BotFather) |
| `TELEGRAM_CHAT_ID` | ✅ | ID del chat/canal de alertas |
| `GLASSNODE_API_KEY` | ✅ | Glassnode API key |
| `COINGECKO_API_KEY` | ⬜ | CoinGecko Pro (más requests/min) |
| `ETHERSCAN_API_KEY` | ⬜ | Etherscan para tokens ERC-20 |
| `SENTRY_DSN` | ⬜ | Sentry error tracking |

### Base de Datos

| Variable | Default | Descripción |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://crypto:crypto@postgres:5432/crypto_db` | URL de PostgreSQL |
| `REDIS_URL` | `redis://redis:6379/0` | URL de Redis |

### Capital y Exchanges

| Variable | Default | Descripción |
|---|---|---|
| `CAPITAL_TOTAL_USD` | `1000.0` | Capital total en USD |
| `MEXC_ALLOCATION_PCT` | `69.0` | Porcentaje asignado a MEXC |
| `BITGET_ALLOCATION_PCT` | `31.0` | Porcentaje asignado a Bitget |
| `PAPER_TRADING` | `true` | **Modo paper trading** (sin dinero real) |

> ⚠️ **Importante**: El sistema arranca en `PAPER_TRADING=true` por defecto. Para operar con dinero real, pon `PAPER_TRADING=false` y verifica que las API keys tienen permisos de trading.

### Umbrales de Detección

| Variable | Default | Descripción |
|---|---|---|
| `ALERT_THRESHOLD` | `70.0` | Score mínimo para emitir alerta (0-100) |
| `DISCOVERY_MIN_MCAP_USD` | `5000000` | Market cap mínimo ($5M) |
| `DISCOVERY_MAX_MCAP_USD` | `500000000` | Market cap máximo ($500M) |
| `DISCOVERY_MIN_VOLUME_USD` | `500000` | Volumen 24h mínimo |
| `DISCOVERY_MAX_TOKEN_AGE_DAYS` | `365` | Edad máxima del token |
| `INFLOW_4H_THRESHOLD_USD` | `500000` | Umbral de inflow 4h para señal fuerte |
| `SHORT_INTEREST_THRESHOLD_PCT` | `20.0` | Short interest mínimo para squeeze |
| `HOLDER_TOP10_THRESHOLD_PCT` | `60.0` | Concentración de holders para pump |

### Riesgo y Stop Loss

| Variable | Default | Descripción |
|---|---|---|
| `STOP_LOSS_PCT` | `8.0` | Stop loss (8% bajo entrada) |
| `DAILY_DRAWDOWN_LIMIT_USD` | `150.0` | Máxima pérdida diaria |
| `MAX_CONCURRENT_POSITIONS` | `3` | Posiciones abiertas simultáneas |
| `CIRCUIT_BREAKER_HOURS` | `24` | Horas de pausa tras 3 pérdidas seguidas |
| `POSITION_SIZE_PCT` | `10.0` | % del capital por operación |

### Modelos y Timing

| Variable | Default | Descripción |
|---|---|---|
| `CLAUDE_MODEL` | `claude-sonnet-4-20250514` | Modelo de Claude a usar |
| `DISCOVERY_INTERVAL_HOURS` | `6` | Frecuencia de escaneo |
| `MONITOR_INTERVAL_SECONDS` | `300` | Frecuencia de polling |
| `JWT_SECRET_KEY` | — | Secreto para JWT del Dashboard |
| `JWT_ALGORITHM` | `HS256` | Algoritmo JWT |
| `JWT_EXPIRE_MINUTES` | `60` | Expiración del token JWT |

---

## Ejecutar el Sistema

### Iniciar todo

```bash
docker compose up -d
```

### Comandos útiles

```bash
# Ver logs de un agente específico
docker compose logs -f discovery
docker compose logs -f detector
docker compose logs -f executor

# Reiniciar un agente
docker compose restart executor

# Ver estado de salud
curl http://localhost:8080/health

# Ver métricas Prometheus de un agente
curl http://localhost:9102/metrics  # Detector

# Acceder al Dashboard API
curl -X POST http://localhost:8001/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<JWT_SECRET_KEY>"}'

# Detener todo (conserva datos)
docker compose down

# Detener y eliminar todos los datos
docker compose down -v
```

### Verificar migraciones

```bash
docker compose exec orchestrator python -m alembic current
docker compose exec orchestrator python -m alembic history
```

---

## Dashboard — API Reference

Base URL: `http://localhost:8001`

Todos los endpoints (excepto `/auth/login`) requieren header `Authorization: Bearer <token>`.

### Autenticación

| Método | Endpoint | Descripción |
|---|---|---|
| `POST` | `/auth/login` | Login, retorna access_token |
| `POST` | `/auth/refresh` | Renovar token |
| `GET` | `/auth/me` | Info del usuario actual |

### Tokens

| Método | Endpoint | Descripción |
|---|---|---|
| `GET` | `/tokens` | Lista tokens activos (`?exchange=mexc&min_score=70`) |
| `GET` | `/tokens/{symbol}` | Detalle de un token con historial de scores |

### Trades

| Método | Endpoint | Descripción |
|---|---|---|
| `GET` | `/trades` | Lista trades (`?status=open&symbol=COLLECT`) |
| `GET` | `/trades/summary` | Resumen: win rate, PnL total, métricas |
| `POST` | `/trades/execute` | Abrir trade manual (paper o real) |
| `POST` | `/trades/{id}/close` | Cerrar trade manualmente |

### Configuración

| Método | Endpoint | Descripción |
|---|---|---|
| `GET` | `/config` | Ver configuración actual (runtime + settings) |
| `PUT` | `/config` | Actualizar umbrales en tiempo real (sin reiniciar) |

### Agentes

| Método | Endpoint | Descripción |
|---|---|---|
| `GET` | `/agents/health` | Estado de salud de todos los agentes |
| `POST` | `/agents/{name}/trigger` | Forzar ciclo inmediato de un agente |
| `GET` | `/agents/circuit-breaker` | Estado del circuit breaker |
| `POST` | `/agents/circuit-breaker/reset` | Resetear circuit breaker manualmente |

### WebSocket

```javascript
// Conectar al stream en tiempo real
const ws = new WebSocket('ws://localhost:8001/ws?token=<jwt_token>');

ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    // msg.channel: uno de los canales Redis
    // msg.data: payload del evento
    console.log(msg.channel, msg.data);
};
```

Los canales disponibles son:
- `channel:detector:scored_token` — Nuevo token puntuado
- `channel:executor:trade_result` — Trade ejecutado
- `channel:learner:feedback` — Actualización de pesos

---

## Cómo Agregar un Nuevo Exchange

El sistema usa CCXT como abstracción, por lo que añadir un nuevo exchange requiere cambios en 4 lugares:

### 1. Variables de entorno (`.env` y `shared/config/settings.py`)

```python
# settings.py — agregar tras las variables de Bitget:
newex_api_key: SecretStr = Field(default=SecretStr(""), alias="NEWEX_API_KEY")
newex_secret_key: SecretStr = Field(default=SecretStr(""), alias="NEWEX_SECRET_KEY")
newex_allocation_pct: float = Field(0.0, ge=0, le=100, alias="NEWEX_ALLOCATION_PCT")

@property
def newex_capital_usd(self) -> float:
    return self.capital_total_usd * (self.newex_allocation_pct / 100)
```

### 2. ExchangeScanner (`agents/discovery/exchange_scanner.py`)

```python
# Añadir en EXCHANGE_IDS:
EXCHANGE_IDS = ["mexc", "bitget", "newex"]

# Añadir en _create_exchange():
elif exchange_id == "newex":
    return ccxt.async_support.newex({
        "apiKey": settings.newex_api_key.get_secret_value(),
        "secret": settings.newex_secret_key.get_secret_value(),
        "enableRateLimit": True,
    })
```

### 3. ExchangeClient (`agents/executor/exchange_client.py`)

```python
# Añadir en _get_exchange():
elif exchange == "newex":
    return ccxt.async_support.newex({
        "apiKey": settings.newex_api_key.get_secret_value(),
        "secret": settings.newex_secret_key.get_secret_value(),
    })
```

### 4. DataFetcher (`agents/monitor/data_fetcher.py`)

```python
# Añadir en _get_ccxt_exchange():
elif exchange == "newex":
    return ccxt.async_support.newex({"enableRateLimit": True})
```

### 5. Verificar

```bash
docker compose restart discovery monitor executor
docker compose logs -f discovery | grep "newex"
```

---

## Interpretar las Métricas del Learner

El Learner genera un reporte semanal cada lunes por Telegram y lo guarda en `learning_logs`. Cada métrica indica:

### Win Rate por Patrón

```
long_pump   ████████░░  78%  (21/27 trades)
classic     ██████░░░░  62%  (8/13 trades)
```

- **>70%**: El detector identifica bien este patrón. Pesos estables.
- **50-70%**: Rendimiento aceptable. El Learner ajusta ligeramente.
- **<50%**: El patrón genera demasiados falsos positivos. El Learner reducirá el peso de sus señales.

### Entry Quality Distribution

```
perfect  ███░░░░░░░  32%  (score>85, precio no movido)
good     █████░░░░░  48%  (score>70, entrada limpia)
early    ██░░░░░░░░  15%  (score correcto, precio bajó antes de subir)
late     █░░░░░░░░░   5%  (entrada tarde, menos ganancia)
```

- **perfect + good > 70%**: El ScoreEngine calibra bien el timing.
- **early > 20%**: Bajar ligeramente `ALERT_THRESHOLD` o aumentar peso de `lp_inflow`.
- **late > 15%**: Subir `ALERT_THRESHOLD` o revisar velocidad del monitor.

### Ajuste de Pesos (WeightUpdate)

Cuando el Learner actualiza pesos, publica en Redis y el Detector los aplica sin reiniciar:

```json
{
  "lp_inflow": 1.4,
  "lp_holder": 0.9,
  "lp_price_stability": 1.1,
  "lp_short_pressure": 0.8,
  "cs_short_interest": 1.3,
  "cs_funding_rate": 1.5,
  "cs_inflow_activator": 0.7,
  "cs_strong_holder": 1.0
}
```

Todos los pesos se mantienen en el rango `[0.3, 3.0]`. Un peso de `1.0` es neutro (sin amplificación).

### PnL y Drawdown

```
PnL total:        +$342.50  (+34.25%)
PnL semana:       +$87.20
Drawdown máximo:  -$48.00   (-4.8%)
Circuit breaker:  0 activaciones
```

- Si el **drawdown máximo supera $150** en un día, el circuit breaker para el trading 24h.
- El Orchestrator notifica por Telegram cuando esto ocurre y cuando se reactiva.

---

## Troubleshooting

### Los agentes no se conectan a PostgreSQL

```bash
# Verificar que postgres está healthy
docker compose ps postgres

# Ver logs de postgres
docker compose logs postgres

# Forzar reinicio del orchestrator (re-corre migraciones)
docker compose restart orchestrator
```

### El Detector no recibe snapshots del Monitor

```bash
# Verificar que Redis está corriendo
docker compose exec redis redis-cli ping  # debe responder PONG

# Ver mensajes en el canal
docker compose exec redis redis-cli subscribe channel:monitor:pump_signal
# (esperar el próximo ciclo del monitor, cada 5 min)
```

### No llegan alertas al Telegram

1. Verificar `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` en `.env`
2. Asegurarse de haber iniciado una conversación con el bot
3. Revisar logs del scorer: `docker compose logs -f scorer`
4. El score debe superar `ALERT_THRESHOLD` (default 70) — puede ser que los tokens actuales no califiquen

### Circuit breaker activo

```bash
# Ver estado
curl http://localhost:8001/agents/circuit-breaker \
  -H "Authorization: Bearer <token>"

# Resetear manualmente (solo si se verificaron las causas)
curl -X POST http://localhost:8001/agents/circuit-breaker/reset \
  -H "Authorization: Bearer <token>"
```

### Paper trading activado pero quiero trading real

1. Detener el sistema: `docker compose down`
2. Editar `.env`: `PAPER_TRADING=false`
3. Verificar que las API keys de MEXC y Bitget tienen permisos de **spot trading**
4. Reiniciar: `docker compose up -d`
5. Confirmar en logs: `docker compose logs executor | grep "REAL TRADING"`

> ⚠️ **Advertencia**: El sistema operará con dinero real. Verifica el capital configurado en `CAPITAL_TOTAL_USD` antes de activar.

---

## Estructura del Proyecto

```
crypto_agent_system/
├── agents/
│   ├── discovery/          # Escaneo de exchanges + filtrado
│   ├── monitor/            # Polling de precios y on-chain data
│   ├── detector/           # Score engine + Claude validation
│   ├── scorer/             # Alertas Telegram
│   ├── executor/           # Trading paper/real + risk manager
│   ├── learner/            # Evaluación + XGBoost optimization
│   └── dashboard/          # FastAPI REST + WebSocket
├── orchestrator/           # Supervisor + Claude market advisor
├── shared/
│   ├── config/             # Settings (Pydantic BaseSettings)
│   ├── models/             # SQLAlchemy models
│   ├── redis_bus/          # Pub/Sub bus
│   └── utils/              # Logging, retry decorators
├── alembic/                # Migraciones de base de datos
├── tests/
│   ├── unit/               # Tests por módulo (sin I/O real)
│   └── integration/        # Tests de flujo completo (mocked)
├── docker/                 # prometheus.yml, grafana config
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## Ejecutar Tests

```bash
# Instalar dependencias de desarrollo
pip install -r requirements.txt

# Correr todos los tests
pytest tests/ -v

# Correr solo tests unitarios
pytest tests/unit/ -v

# Correr solo tests de integración
pytest tests/integration/ -v

# Con cobertura
pytest tests/ --cov=agents --cov=shared --cov-report=term-missing

# Test específico
pytest tests/unit/test_pre_screener.py -v
pytest tests/integration/test_monitor_to_executor.py::TestDetectorScoring -v
```

---

## Caso de Estudio — Origen del Sistema

El sistema está inspirado en la estrategia del canal **KManuS88** que documentó cómo identificar "Criminal Pumps" en el mercado cripto:

- **Capital inicial**: $640
- **Capital final**: $1,752
- **Período**: 60-80 días
- **Exchanges**: MEXC (posiciones principales) + Bitget (hedge)

### Señales clave identificadas

**Long Pump** (token siendo acumulado para pump):
- Inflow de exchange superior en las últimas 4h (smart money entrando)
- Concentración de holders en top 10 wallets > 60%
- Precio estable mientras el volumen aumenta (acumulación silenciosa)
- Funding rate positivo (longs dominan, shorts en desventaja)

**Classic Short Squeeze** (shorts atrapados):
- Short interest > 20% del float
- Funding rate muy negativo (shorts pagando)
- Inflow súbito de 1h (catalizador del squeeze)
- Holders concentrados (fácil de mover el precio)

El **Score Engine** combina ambos patrones y aplica un bonus de convergencia cuando ambos superan 50 puntos simultáneamente, identificando los setups de mayor probabilidad.

---

## Licencia

MIT — Úsalo bajo tu propio riesgo. Este sistema no constituye asesoramiento financiero. El trading de criptomonedas conlleva riesgo de pérdida total del capital.
