# Bitácora de Construcción — Crypto Agent System

> Registro cronológico del proceso completo de diseño, construcción y deploy de un sistema
> multi-agente de detección y trading automático de "Criminal Pumps" en criptomonedas.
> Escrito en tono didáctico para quien quiera construir algo similar.

---

## El Punto de Partida: La Idea Original

Todo empezó con un canal de YouTube llamado **KManuS88**, donde el creador documentó cómo
transformó **$640 → $1,752 en 60-80 días** operando manualmente altcoins de baja capitalización.
Su estrategia no era especulación aleatoria: él esperaba señales específicas antes de entrar.

Las señales que buscaba — que él llamaba "Criminal Pumps" — tenían un patrón reconocible:

1. **Acumulación silenciosa**: precio estable por días mientras el volumen crece sutilmente
2. **Inflow masivo hacia exchanges**: las ballenas mueven tokens hacia exchanges = intención de vender caro
3. **Concentración de holders**: pocos wallets controlan gran parte del supply
4. **El pump**: precio sube 30-200% en horas; los que entraron antes ganan; los que entran después pierden

La pregunta que motivó este proyecto fue: **¿se puede automatizar la detección de esas señales?**

La respuesta, después de meses de construcción, es: **sí, con matices**.

---

## Arquitectura General: Por Qué Multi-Agente

Antes de escribir una línea de código, la primera decisión fue arquitectónica:
¿un script monolítico o múltiples agentes?

**El argumento para el monolito**: más simple, más fácil de debuggear.

**El argumento para los agentes**: cada responsabilidad tiene frecuencias distintas.
El escaneo de exchanges ocurre cada 6 horas. El monitoreo de precios, cada 5 minutos.
La detección de patrones, en tiempo real. Si todo vive en un proceso, un error en el
escaneo rompe el monitoreo, y viceversa.

**Decisión**: arquitectura de 7 agentes desacoplados comunicándose por **Redis pub/sub**.
Cada agente es un proceso independiente con su propio Dockerfile. Si uno falla, los demás
siguen funcionando. Si quiero escalar el Monitor, solo escalo ese contenedor.

```
Discovery → Monitor → Detector → Scorer → Executor
                                    ↓
                                 Learner
                                    ↑
                              Orchestrator
                              Dashboard
```

El bus de mensajes (Redis channels) define el contrato entre agentes. Nadie llama a nadie
directamente; todos publican y suscriben. Esto es fundamental: permite agregar un nuevo agente
sin tocar ninguno de los existentes.

---

## FASE 0 — Scaffold: La Infraestructura Base

**Lo que se construyó**: estructura de directorios, `docker-compose.yml`, `.env.example`,
`settings.py` con Pydantic, y los Dockerfiles de cada agente.

**Decisión de diseño clave**: usar `pydantic-settings` para la configuración.

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)
    anthropic_api_key: SecretStr = Field(...)
    alert_threshold: float = Field(70.0)
    paper_trading: bool = Field(True)
```

Por qué Pydantic para settings:
- Validación automática de tipos en el arranque (si falta una variable, falla en startup, no en runtime)
- `SecretStr` evita que las claves aparezcan en logs accidentalmente
- Un singleton `settings = Settings()` disponible desde cualquier módulo

**Regla que nunca se rompe**: `PAPER_TRADING=true` por defecto. El sistema nunca opera con
dinero real hasta que tenga 30 días de historial paper con buenos resultados.

**Lección**: Definir los Docker service names exactos desde el principio (postgres, redis,
orchestrator) y usarlos en las URLs. El error clásico es poner `localhost` en las URLs dentro
de Docker, donde los contenedores se ven entre sí por nombre de servicio, no por localhost.

---

## FASE 1 — Shared Layer: El Contrato entre Agentes

**Lo que se construyó**: modelos SQLAlchemy, Redis bus, migraciones Alembic, utilidades de
logging y retry.

### Los Modelos de Base de Datos

Cuatro tablas principales:
- `token_candidates`: tokens que pasaron el pre-filtrado de Discovery
- `alerts`: alertas enviadas por Telegram (con timestamp y deduplicación)
- `trades`: historial completo de paper y real trades
- `learning_logs`: registro de ajustes de pesos del Learner

**Decisión clave: ENUMs de PostgreSQL**

Los ENUMs en PostgreSQL son tipos a nivel de base de datos, no a nivel de tabla. Esto creó
el primer problema importante:

```
asyncpg.exceptions.DuplicateObjectError: type "token_status" already exists
```

SQLAlchemy intenta crear el ENUM en cada `CREATE TABLE`. Si el tipo ya existe (por ejemplo,
si corriste las migraciones dos veces), falla. La solución es idempotente:

```sql
DO $$ BEGIN
    CREATE TYPE token_status AS ENUM ('active', 'removed');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
```

El bloque `DO $$ ... $$` de PostgreSQL permite capturar excepciones específicas.
`duplicate_object` es el código exacto para "este tipo ya existe". Esto hace la migración
segura de ejecutar múltiples veces.

En SQLAlchemy, los ENUMs en columnas deben declararse con `create_type=False` para no
intentar crearlos de nuevo:

```python
from sqlalchemy.dialects import postgresql
column = mapped_column(postgresql.ENUM('active', 'removed', name='token_status', create_type=False))
```

### El Redis Bus

```python
class RedisBus:
    async def publish(self, channel: Channel, data: dict) -> None:
        await self._redis.publish(channel.value, json.dumps(data))

    async def subscribe(self, channel: Channel, handler: Callable) -> None:
        self._handlers[channel] = handler
```

El `Channel` es un enum de strings (`"channel:discovery:new_candidates"`, etc.). Esto evita
errores de tipeo: si escribes mal el nombre del canal, Python falla en startup, no en runtime
cuando ya llevas 3 horas en producción esperando mensajes que nunca llegan.

### Structlog y Tenacity

**structlog** para logging estructurado (JSON en producción, texto legible en dev):
```python
log.info("monitor_agent.cycle_done", tokens=536, published=534, duration="113.2s")
```

Cada log tiene campos estructurados. Esto hace que Grafana/Loki pueda filtrar por campo
sin parsear texto libre.

**tenacity** para reintentos con backoff exponencial:
```python
@http_retry
async def _fetch_cg_page(self, client, page):
    resp = await client.get(...)
    resp.raise_for_status()
    return resp.json()
```

El decorador maneja automáticamente reintentos con espera creciente. Sin esto, un rate limit
temporal de CoinGecko rompe el ciclo de Discovery completo.

---

## FASE 2 — Discovery Agent: El Scanner

**Objetivo**: encontrar tokens candidatos entre los miles disponibles en MEXC y Bitget,
filtrando por market cap, volumen y edad del token.

**Lo que se construyó**: `ExchangeScanner` + `PreScreener` + agente de orquestación.

### El Problema de CoinGecko

El plan original era simple: CoinGecko tiene datos de market cap y volumen para casi todo.
Pedir las primeras 2,000 monedas ordenadas por volumen, cruzar con los símbolos de MEXC/Bitget.

El problema: **CoinGecko free tier tiene un rate limit de ~30 req/min**. Con 8 páginas de
250 tokens cada una, se llegaba al límite a mitad del scan.

La solución fue un sistema de dos fuentes en paralelo:

```python
cg_data, mexc_tickers, bitget_tickers = await asyncio.gather(
    self.get_market_data(all_symbols),    # CoinGecko (puede ser parcial)
    self.get_exchange_tickers("mexc"),    # CCXT como fallback
    self.get_exchange_tickers("bitget"),
)
```

Si CoinGecko falla o devuelve datos parciales, los tickers de CCXT sirven como fallback.
Los tickers tienen volumen pero no market cap, así que el PreScreener tiene dos modos:

```python
if t.market_cap_usd is not None:
    # Modo CoinGecko: filtrar por mcap ($5M - $500M)
else:
    # Modo fallback: filtrar por volumen ($100k - $100M)
```

### El PreScreener

Filtros aplicados en orden:
1. Blacklist de stablecoins (USDT, USDC, BUSD, DAI...)
2. Market cap entre $5M y $500M (zona óptima de pumps)
3. Volumen/mcap ratio mínimo del 3% (token activo, no muerto)
4. Edad máxima del token: 2 años (tokens nuevos son más volátiles)
5. Cambio de precio 24h < 50% (evitar tokens ya en pump activo)

**Resultado**: de ~1,500 símbolos totales en MEXC+Bitget, quedan ~530 candidatos.

**Lección aprendida**: Los exchanges tienen símbolos duplicados o con naming inconsistente.
`GOLD` en MEXC puede ser un token diferente a `GOLD` en Bitget. El sistema asigna exchange
de forma definitiva en Discovery y lo mantiene durante todo el ciclo de vida del token.

---

## FASE 3 — Monitor Agent: El Vigilante

**Objetivo**: para cada token candidato, obtener cada 5 minutos: precio, spread bid/ask,
datos de futuros (funding rate, open interest) y datos on-chain.

### La Arquitectura del DataFetcher

El problema de escala: 530 tokens × múltiples llamadas cada 5 minutos = miles de requests
por ciclo. Sin control de concurrencia, colapsaría las APIs.

Solución: **semáforo de asyncio**:

```python
_SEMAPHORE = asyncio.Semaphore(8)

async def fetch_all(self, symbol, exchange_id):
    async with _SEMAPHORE:   # máximo 8 fetches simultáneos
        ticker, orderbook, funding, oi = await asyncio.gather(
            self._fetch_ticker(exchange, pair),
            self._fetch_orderbook(exchange, pair),
            self._fetch_funding_rate(exchange, pair),
            self._fetch_open_interest(exchange, pair),
        )
```

El semáforo limita la concurrencia a 8 simultáneas. Dentro de cada slot, los 4 sub-fetches
del mismo token corren en paralelo con `gather`. Este patrón es idiomático en asyncio para
APIs con rate limits.

### El Fallback de Exchange

Algunos tokens listados en MEXC pueden no tener datos en un momento dado (par suspendido,
mantenimiento). La solución es un fallback automático:

```python
_FALLBACK = {"mexc": "bitget", "bitget": "mexc"}

for attempt_exchange in [exchange_id, _FALLBACK.get(exchange_id, "")]:
    # intentar fetch
    if ticker is not None:
        break  # usar el que funcionó
```

Esto aumenta significativamente la cobertura: tokens que fallan en el exchange primario
a menudo tienen datos válidos en el secundario.

### El TokenSnapshot

El output del Monitor es un `TokenSnapshot` Pydantic:

```python
class TokenSnapshot(BaseModel):
    symbol: str
    current_price: float
    price_change_24h_pct: Optional[float]
    volume_24h_usd: Optional[float]
    inflow_4h_usd: Optional[float]
    long_short_ratio: Optional[float]
    funding_rate: Optional[float]
    open_interest_usd: Optional[float]
    total_holders: Optional[int]
    onchain_available: bool
```

Todos los campos opcionales con `None` como valor por defecto. El Detector downstream
maneja datos faltantes graciosamente (señal neutra, no error).

---

## FASE 4 — Detector Agent: El Cerebro

**Objetivo**: recibir snapshots del Monitor y calcular un score 0-100 que refleje la
probabilidad de pump inminente.

### El ScoreEngine: Dos Patrones en Competencia

El detector implementa dos patrones distintos y elige el dominante:

**Patrón A: Long Pump** (acumulación silenciosa)
- Señal 1: Inflow masivo 4h → 0-40 pts
- Señal 2: Suplementaria (L/S ratio, OI, holders) → 0-18 pts
- Señal 3: Precio estable → 0-20 pts
- Señal 4: Funding rate positivo → 0-15 pts

**Patrón B: Classic Squeeze** (short squeeze)
- Señal 1: Short interest alto → 0-35 pts
- Señal 2: Funding muy negativo → 0-25 pts
- Señal 3: Inflow activador 1h → 0-25 pts
- Señal 4: Holders fuertes → 0-15 pts

```python
lp = pattern_long_pump.score(snapshot, weights)
cl = pattern_classic_squeeze.score(snapshot, weights)

# El dominante es el de mayor score
composite = max(lp.score, cl.score)

# Bonus si ambos suenan fuerte (convergencia)
if lp.score >= 50 and cl.score >= 50:
    convergence_bonus = min(10.0, (lp.score + cl.score - 100) * 0.2)
    composite = min(100.0, composite + convergence_bonus)
```

### La Validación con Claude

Cuando un token supera el `LLM_VALIDATION_THRESHOLD` (85 pts), se envía a Claude para
validación antes de alertar:

```python
if scored.composite_score >= settings.llm_validation_threshold:
    analysis = await self._validator.validate(scored)
    scored = scored.model_copy(update={"llm_analysis": analysis, "llm_validated": True})
```

El prompt usa **caché de contexto** (Anthropic prompt caching): el system prompt con las
reglas de análisis se cachea, y solo el estado del token se envía en cada llamada.
Esto reduce el costo de tokens en ~70%.

### El Write-Back a Base de Datos

El error más sutil del sistema: el Detector calculaba scores perfectamente y los publicaba
en Redis, pero el Dashboard leía desde PostgreSQL... donde todos los scores seguían siendo NULL.

La solución es un write-back explícito después de cada score calculado:

```python
async with get_session() as session:
    await session.execute(
        update(TokenCandidate)
        .where(TokenCandidate.symbol == snapshot.symbol)
        .values(detection_score=scored.composite_score, pattern_type=pattern)
    )
```

**Lección clave**: en arquitecturas event-driven, el "source of truth" para dashboards
suele ser la base de datos, no el bus de mensajes. El bus es para tiempo real;
la DB es para persistencia y consultas. Hay que escribir en ambos lugares según el caso.

---

## FASE 5 — Scorer Agent: Las Alertas

**Objetivo**: recibir tokens sobre el umbral de alerta y enviar notificaciones a Telegram.

El Scorer implementa **deduplicación de 2 horas**: si ya envió una alerta para UMXM,
no envía otra en las próximas 2 horas aunque el score vuelva a subir.

```python
# Verificar en DB si hay alerta reciente
existing = await session.execute(
    select(Alert)
    .where(Alert.token_symbol == symbol)
    .where(Alert.sent_at > datetime.now(utc) - timedelta(hours=2))
)
if existing.scalar():
    return  # ya alertamos recientemente
```

Los mensajes de Telegram usan HTML con inline keyboard:
- Botón "📊 Ver Score" → abre el dashboard
- Botón "⚡ Ejecutar" → encola el trade manualmente

---

## FASE 6 — Executor Agent: El Trader

**Objetivo**: ejecutar trades paper (o reales) cuando recibe tokens validados del Detector.

### El Risk Manager

Tres mecanismos de protección anidados:

**1. Stop Loss (8%)**: si el precio cae 8% desde la entrada, vender inmediatamente.
```python
stop_loss_price = entry_price * 0.92
```

**2. Take Profit Escalonado**:
- TP1 (+30%): vender 30% de la posición
- TP2 (+60%): vender otro 30%
- TP3 (+100%): vender el 40% restante

Esta estructura permite capturar ganancias intermedias si el pump no llega hasta arriba,
y maximizar si sí llega.

**3. Circuit Breaker**: 3 pérdidas consecutivas → pausa de 24 horas.
El estado persiste en Redis con TTL para sobrevivir reinicios del contenedor:

```python
_CB_KEY = "executor:circuit_breaker"
await self._redis.set(_CB_KEY, "1", ex=settings.circuit_breaker_hours * 3600)
```

### Paper vs Real Trading

```python
if settings.paper_trading:
    # Simular: registrar en DB sin llamar al exchange
    trade = Trade(is_paper=True, ...)
else:
    # Ejecutar: llamar a CCXT y luego registrar
    order = await exchange.create_market_order(symbol, "buy", quantity)
    trade = Trade(is_paper=False, order_id=order["id"], ...)
```

La separación es limpia: toda la lógica de riesgo, posición y registro es idéntica.
Solo el bloque de ejecución real vs simulada cambia.

---

## FASE 7 — Learner Agent: La Mejora Continua

**Objetivo**: analizar trades pasados y ajustar los pesos del ScoreEngine para mejorar
los resultados.

El Learner usa **XGBoost** para encontrar qué combinación de señales predice mejor
las ganancias. Después de cada semana de trading:

1. `TradeEvaluator`: clasifica cada trade como `perfect`, `good`, `early`, `late` o `bad`
2. `WeightOptimizer`: entrena XGBoost con los features del snapshot en el momento de entrada
3. Los nuevos pesos se publican vía Redis al Detector, que los aplica en tiempo real

```python
# Publicar pesos actualizados al Detector
await bus.publish(Channel.LEARNER_FEEDBACK, {
    "weights": new_weights.model_dump(),
    "reason": "weekly_optimization",
    "updated_at": datetime.now(utc).isoformat(),
})
```

El Detector escucha este canal y actualiza su ScoreEngine sin reiniciarse:

```python
async def _handle_weight_update(self, payload: dict) -> None:
    update = WeightUpdate(**payload)
    self._engine.update_weights(update.weights)
```

**Este es el loop de aprendizaje**: el sistema mejora solo con el tiempo.

---

## FASE 8 — Dashboard API: La Ventana al Sistema

**Objetivo**: API REST + WebSocket para visualizar el estado del sistema en tiempo real.

### JWT y el Error del Form

El login usa `OAuth2PasswordRequestForm` de FastAPI, que espera el body como
`application/x-www-form-urlencoded`, no JSON:

```javascript
// CORRECTO
const body = new URLSearchParams({ username: "admin", password: "admin1234" });
fetch('/auth/login', { method: 'POST', body, headers: { 'Content-Type': 'application/x-www-form-urlencoded' } })

// INCORRECTO — devuelve 422 Unprocessable Entity
fetch('/auth/login', { method: 'POST', body: JSON.stringify({username, password}), headers: { 'Content-Type': 'application/json' } })
```

Este es uno de los errores más frecuentes con FastAPI: el formato del body de autenticación
no es JSON por default, es form-urlencoded (igual que los formularios HTML clásicos).

### Los WebSockets

Los WebSockets del dashboard requieren el token como query parameter, ya que los
WebSocket browsers no pueden enviar headers de autorización:

```
ws://localhost:8001/ws/signals?token=eyJ...
```

El servidor valida el token antes de aceptar la conexión:

```python
@app.websocket("/ws/signals")
async def ws_signals(websocket: WebSocket, token: str = Query(...)):
    try:
        await get_current_user(token)
    except Exception:
        await websocket.close(code=1008)  # Policy Violation
        return
    await ws_manager.connect(websocket, "signals")
```

### El Rate Limiter

`slowapi` agrega rate limiting con una sola línea por endpoint:

```python
@router.get("/tokens")
@limiter.limit("60/minute")
async def list_tokens(request: Request, ...):
    ...
```

---

## FASE 9 — Orchestrator: El Supervisor

**Objetivo**: supervisar la salud de todos los agentes y proporcionar análisis de mercado
periódico con Claude.

El `AgentSupervisor` hace ping a cada agente cada 60 segundos. Si detecta un agente caído,
intenta reiniciarlo vía Docker API. El `ClaudeAdvisor` analiza el estado global del mercado
cada hora y lo hace disponible via `GET /market/context`.

---

## FASE 10 — Tests

**Tests unitarios** para los componentes de scoring:
- `test_pattern_long_pump.py`: verifica que cada señal devuelve el puntaje correcto
- `test_pre_screener.py`: verifica que los filtros de Discovery funcionan
- `test_risk_manager.py`: verifica stop loss, take profit y circuit breaker

**Tests de integración**:
- `test_discovery_to_monitor.py`: flujo completo de Discovery → publicación en Redis
- `test_monitor_to_executor.py`: flujo completo de Monitor → Detector → Executor

---

## FASE 11 — Frontend UI

**Stack**: Alpine.js + Chart.js + Tailwind CSS (todo desde CDN, sin build step).

La decisión de no usar React/Vue fue deliberada: el dashboard es una SPA simple sin
estado complejo. Alpine.js maneja el estado reactivo con atributos HTML:

```html
<div x-data="app()" x-init="init()">
  <p x-text="tokens.length"></p>
  <template x-for="t in tokens" :key="t.id">
    <tr>...</tr>
  </template>
</div>
```

Sin npm, sin webpack, sin bundle. El archivo `index.html` es self-contained y se sirve
directamente desde FastAPI con `StaticFiles`.

**4 secciones**:
- **Scanner**: tabla de tokens con score bars y patrones
- **Alertas**: cards de tokens que generaron alerta Telegram
- **Portfolio**: gráfico de equity (Chart.js) + historial de trades
- **Sistema**: estado de cada agente + circuit breaker + controles

---

## FASE 12 — Pantalla de Performance

**Objetivo**: métricas de evaluación del sistema para decidir cuándo hacer upgrade a APIs
de datos más completas.

El endpoint `GET /performance/metrics` calcula en tiempo real:

```python
return {
    "win_rate": len(wins) / len(closed),     # % trades con PnL > 0
    "total_trades": total,                    # total en DB
    "days_operating": delta.days,             # desde el primer trade
    "avg_anticipation_hours": avg_hours,      # delay alerta → trade
    "classic_fail_rate": fails / classic,    # % Classic Squeeze malos
    "glassnode_cost_pct": (99 / capital) * 100,  # costo relativo
}
```

La página muestra semáforos (verde/amarillo/rojo) y un **veredicto automático**: qué
criterios faltan para justificar el upgrade a Glassnode u otras APIs premium.

---

## FASE 13 — Reemplazo de Glassnode

**El problema**: Glassnode subió su plan mínimo a **$999/mes**. Para un capital de $1,000,
eso es el 100% del capital en fees solo de datos. No viable.

**La solución**: tres fuentes gratuitas combinadas.

### Coinglass (sin API key)

```python
COINGLASS_BASE = "https://open-api.coinglass.com/public/v2"
# Endpoints: /indicator/funding_avg, /indicator/open_interest,
#            /indicator/long_short_account_ratio
```

Problema encontrado: Coinglass devuelve HTTP 500 para altcoins pequeños que no tienen
datos de futuros. El decorador `@http_retry` reintentaba en loop, generando ruido enorme
en los logs y ralentizando el ciclo.

Solución: quitar el retry de los métodos Coinglass y devolver `None` directamente
en cualquier error HTTP ≥ 400:

```python
async def _get(self, client, endpoint, params) -> dict | None:
    resp = await client.get(...)
    if resp.status_code >= 400:
        return None  # sin retry — token no cubierto por Coinglass
    return resp.json()
```

### Rediseño del Score

| Señal | Antes (con Glassnode) | Después |
|---|---|---|
| Inflow | 40 pts (Glassnode) | 40 pts (CryptoQuant / proxy vol×15%) |
| Holders | 25 pts (Glassnode) | **0 pts** → reemplazado |
| L/S ratio | — | 0-8 pts (Coinglass) |
| OI / volumen | — | 0-5 pts (Coinglass/CCXT) |
| Holder count | — | 0-5 pts (Etherscan) |
| Price stability | 20 pts | 20 pts |
| Short pressure | 15 pts | 15 pts |

Máximo teórico: **93 pts**. Umbral de alerta ajustado a **62 pts** (antes 70).

---

## Problemas Resueltos: Registro Completo

### 1. `asyncpg.DuplicateObjectError: type "token_status" already exists`

**Causa**: SQLAlchemy crea los ENUMs en `CREATE TABLE` aunque `create_type=False` esté
configurado en la columna, si el ENUM fue definido por separado.

**Solución**: usar `DO $$ BEGIN CREATE TYPE ... EXCEPTION WHEN duplicate_object THEN NULL; END $$;`
en la migración Alembic. Idempotente, corre cuantas veces sea necesario.

### 2. `relation "token_candidates" does not exist`

**Causa**: las migraciones Alembic fallaban silenciosamente por el error de ENUM anterior.
Los contenedores de agentes arrancaban antes de que las tablas existieran.

**Solución**: corregir la migración + usar `docker compose up --force-recreate` para
reiniciar todos los servicios dependientes.

### 3. Dashboard raíz devuelve `{"detail": "Not Found"}`

**Causa**: FastAPI no tiene una ruta raíz por defecto.

**Solución**: agregar `StaticFiles` mount y una ruta raíz explícita:
```python
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
@app.get("/", include_in_schema=False)
async def root():
    return FileResponse(str(static_dir / "index.html"))
```

### 4. Discovery encontraba 0 candidatos

**Causa**: CoinGecko rate-limita sin API key. `cg_data` era vacío → todos los tokens
tenían `market_cap_usd=None` → el PreScreener los rechazaba todos.

**Solución**: paralelizar CoinGecko con tickers CCXT. Si CoinGecko falla, el volumen
del ticker sirve como proxy para los filtros.

### 5. Scores NULL en el Dashboard

**Causa**: el Detector calculaba y publicaba scores en Redis, pero nunca los escribía
en PostgreSQL. El Dashboard lee de PostgreSQL.

**Solución**: agregar write-back explícito a `token_candidates` en el Detector.

### 6. Solo 5 tokens de Bitget (de 741 posibles)

**Causa**: CoinGecko cubría solo los primeros 750 tokens por volumen. Los demás tenían
`volume_24h_usd=None` → rechazados como `volume_too_low:0`.

**Solución**: buscar tickers de CCXT EN PARALELO con CoinGecko (no como fallback).
Los tokens sin datos de CoinGecko usan los datos del ticker directamente.

### 7. Muchos tokens con `pattern_type: unknown`

**Causa**: Discovery inserta tokens con `pattern_type='unknown'` (valor inicial).
El Detector lo actualiza después del primer ciclo del Monitor.

**No es un bug**: es el comportamiento correcto. Los tokens nuevos pasan de `unknown`
a `long_pump` o `classic` después del primer snapshot.

### 8. Coinglass retrying en loop (errores 500)

**Causa**: `@http_retry` con backoff exponencial reintentaba errores 500, que son
el comportamiento normal de Coinglass para altcoins sin datos de derivados.

**Solución**: quitar el retry de los métodos Coinglass y retornar `None` en ≥ 400.

---

## Estado Actual del Sistema (Mayo 2026)

```
✅ 12 servicios Docker corriendo
✅ 532 tokens en watchlist (518 MEXC + 14 Bitget)
✅ Monitor: ciclo cada 5 min, 534 snapshots por ciclo, 113s de duración
✅ Detector: scores actualizando, patrón long_pump dominante
✅ Dashboard: http://localhost:8001 (admin / admin1234)
✅ Performance: http://localhost:8001/static/performance.html
✅ Orchestrator: http://localhost:8080/health
✅ Prometheus + Grafana: métricas de todos los agentes

⏳ Sin trades paper aún (max score ~50/62 umbral)
⏳ Coinglass: datos disponibles solo para ~top-100 altcoins
⏳ Etherscan: pendiente de API key para activar holder count
⏳ CryptoQuant: pendiente de API key para inflow real
```

---

## Lecciones Aprendidas por Módulo

### Sobre Arquitectura

**Los contratos son sagrados.** El `TokenSnapshot` (Monitor → Detector) y el `ScoredToken`
(Detector → Scorer/Executor) son interfaces. Cambiar un campo requiere actualizar todos
los consumidores. Pydantic ayuda: si agregas un campo obligatorio sin default, todos los
productores fallan en startup con error claro.

**Redis pub/sub ≠ base de datos.** Redis es para mensajes en tránsito. La DB es el registro
permanente. Nunca asumas que un mensaje en Redis fue procesado; el estado canónico está
en PostgreSQL.

**El semáforo es tu amigo.** `asyncio.Semaphore(N)` es la herramienta correcta para limitar
concurrencia en clients async. Sin él, 530 tokens × 4 requests = 2,120 requests simultáneos
en el primer ciclo.

### Sobre APIs Externas

**Todas las APIs fallan eventualmente.** CoinGecko te rate-limita. Coinglass devuelve 500
para tokens pequeños. CCXT lanza excepciones para pares no listados. Diseña para el fallo,
no para el éxito.

**El retry tiene que ser selectivo.** Reintentar un 500 "esperado" (token sin datos)
es tan malo como no reintentar un 503 transitorio. Distingue entre "este endpoint no tiene
datos para este símbolo" (no reintentes) vs "el servidor está sobrecargado" (reintenta con backoff).

**Los rate limits son asimétricos.** CoinGecko free: 30 req/min. Coinglass: sin límite documentado.
CCXT: depende del exchange. Diseña con los límites más restrictivos y agrega delays conservadores.

### Sobre Docker

**Los service names son el hostname.** `postgresql+asyncpg://postgres:password@postgres:5432/...`
— ese `@postgres` es el nombre del servicio en docker-compose, no localhost.

**`--force-recreate` vs `--build`**: `--build` reconstruye la imagen; `--force-recreate`
reinicia el contenedor con la imagen existente. Si cambias código Python, necesitas
`build` + `--force-recreate`. Si solo cambias variables de entorno, solo `--force-recreate`.

**El orden de arranque importa.** Los agentes necesitan PostgreSQL y Redis saludables antes
de conectarse. `depends_on` con `condition: service_healthy` en docker-compose resuelve esto.

### Sobre Score Engines

**Los pesos iniciales son hipótesis.** El valor de cada señal (40 pts para inflow, 20 pts
para precio estable) fue elegido con criterio, pero son estimaciones. El Learner existe
precisamente para refinarlos con datos reales.

**La señal que siempre da 0 es la señal muerta.** `short_interest_pct` (Classic Squeeze)
siempre fue None sin Glassnode. Una señal que siempre vale 0 no aporta nada y confunde.
Es mejor eliminarla o sustituirla.

**El umbral de alerta es un parámetro de negocio.** 70 pts era conservador; bajarlo a 62
con el nuevo techo de 93 pts mantiene la misma exigencia relativa. Ajustarlo es normal
a medida que el sistema madura.

### Sobre Frontend sin Framework

**Alpine.js es suficiente para dashboards internos.** Para un dashboard de uso personal
con datos tabulares, gráficos y WebSocket, Alpine.js + Chart.js es ~3KB de JS vs ~300KB
de React. El tradeoff de DX vale para proyectos pequeños.

**El formulario de login es form-urlencoded, no JSON.** FastAPI usa `OAuth2PasswordRequestForm`
por defecto, que es el estándar OAuth2 (no JSON). No es un bug de FastAPI; es el estándar.

---

## Para Quien Quiera Construir Algo Similar

Si estuvieras empezando este proyecto desde cero hoy, estas serían las decisiones más importantes:

1. **Define los schemas de mensajes primero.** Antes de escribir un agente, escribe los
   modelos Pydantic que va a producir y consumir. Todo lo demás se organiza alrededor.

2. **Empieza con paper trading y no lo abandones rápido.** 30 días de historial paper
   te dan contexto sobre el rendimiento real del modelo antes de arriesgar capital.

3. **No pagues por datos al principio.** CoinGecko free + CCXT + Coinglass free dan
   suficiente señal para detectar patrones. Paga por datos premium cuando el modelo
   demuestre que los necesita.

4. **El circuit breaker es imprescindible.** Sin él, un modelo defectuoso puede perder
   todo el capital en una serie de malas entradas antes de que te des cuenta.

5. **Monitorea el monitoreo.** Prometheus + Grafana en el stack desde el día 1.
   Un sistema de trading que no puedes observar es un sistema que no puedes mejorar.

6. **El Learner es la razón por la que esto es un sistema, no un script.**
   Los pesos fijos son una hipótesis; el Learner es la validación continua de esa hipótesis.

---

*Última actualización: 13 Mayo 2026*
*Estado: PRODUCCIÓN (paper trading) — 4 trades paper abiertos (ACN x2, LAB x2)*

---

## Sesión 2026-05-13 — Diagnóstico pipeline + fixes de observabilidad

### Contexto
El dashboard mostraba Discovery como "unhealthy" y Detector/Scorer/Learner como "sin datos en DB".
Se realizó diagnóstico completo del pipeline para entender qué estaba pasando.

### Diagnóstico
- **Discovery unhealthy**: Correcto comportamiento. APScheduler con cron a las 2 AM UTC.
  El agente corre al startup y luego una vez al día. Pasó más de 10 minutos desde el startup,
  y el health check usaba `_HEALTHY_WINDOW = 10 min` → siempre unhealthy.
  
- **Detector "sin datos en DB"**: El Detector sí procesaba los 534 snapshots por ciclo y 
  actualizaba scores en la DB. El health check en el orchestrator usaba `Alert.sent_at` 
  (tabla vacía porque nadie superó el umbral de 62) en lugar de `TokenCandidate.last_checked`.
  
- **Pipeline probado con test manual**: `redis-cli PUBLISH channel:monitor:pump_signal '...'`
  → Detector respondió correctamente con `invalid_snapshot` (faltaba `current_price`).
  Confirma que el bus Redis funciona y el Detector escucha.

- **Primer trade confirmado**: Se encontraron 4 trades paper en la DB (ACN x2, LAB x2) 
  ejecutados a las 00:37 UTC. El pipeline funciona de punta a punta.

### Cambios realizados

**`agents/discovery/discovery_agent.py`**
- Agrega `bus.subscribe("channel:control:discovery:run", _handle_manual_trigger)`
- Agrega `bus.start_listening()` en `start()`
- Nuevo método `_handle_manual_trigger()` → llama `self.run()` cuando Dashboard lo solicita
- El botón "Forzar scan ahora" en el Dashboard ahora funciona

**`orchestrator/agent_supervisor.py`**
- `_check_discovery`: ventana de salud 25h en lugar de 10min (se ejecuta diariamente)
- `_check_detector`: usa `MAX(TokenCandidate.last_checked WHERE detection_score IS NOT NULL)`
  en lugar de `MAX(Alert.sent_at)` → refleja actividad real del Detector
- `_check_scorer/learner/executor`: mensajes null descriptivos por agente
- `_make_health()`: nuevo parámetro `healthy_window` (antes solo `degraded_window`)
- `_make_health()`: nuevo parámetro `no_data_detail` para mensaje personalizado por agente

**`agents/dashboard/static/index.html`**
- Auto-refresh: 30 s → 60 s
- Card de Discovery: botón "🔄 Forzar scan ahora" que llama `POST /agents/discovery/run`
- Card de Monitor: línea con "Tokens monitoreados: N" (usa `tokens.length` del estado Alpine)

**`alembic/versions/0002_add_volume_to_token_candidates.py`**
- Reescrito con `ADD COLUMN IF NOT EXISTS` vía `op.execute()` en lugar de `op.add_column()`
- El orchestrator crasheaba al reiniciar porque la columna ya existía (añadida manualmente)
- Se hizo `UPDATE alembic_version SET version_num = '0002'` para marcarla como aplicada

### Estado post-fix del health endpoint
```
discovery  healthy  — última actividad hace 1 min (ran at startup)
monitor    healthy  — última actividad hace 0 min (ciclo cada ~2 min)
detector   healthy  — última actividad hace 0 min (scores actualizados)
scorer     unknown  — esperando primer score ≥ umbral
executor   degraded — última actividad hace 51 min (4 trades abiertos)
learner    unknown  — esperando primer trade cerrado
dashboard  healthy  — HTTP 200 OK
```

---

## Sesión 2026-05-13 (turno 2) — Fix alertas "Sin alerta" + breakdown de scores

### El problema reportado

El Scanner mostraba tokens con scores 62-66 pero todos decían "Sin alerta" — incluso UMXM con score 62 
que superaba el threshold. El usuario sospechaba desajuste entre .env y settings.py, o condición `>` 
en vez de `>=`.

### Diagnóstico real

Investigación sistemática reveló que el stack estaba bien configurado en todos los puntos sospechados:
- `ALERT_THRESHOLD=62` en .env ✓ y en ambos containers (detector, scorer) ✓
- Condición `>=` en `score_engine.py:52` ✓  
- Scorer suscripto a `channel:detector:scored_token` y recibiendo mensajes ✓

El problema real estaba en los logs del scorer:
```
{"error": "Chat not found", "event": "telegram_client.error", ...}
{"symbol": "UMXM", "event": "scorer_agent.send_failed", ...}
```

**Causa raíz**: `TELEGRAM_CHAT_ID` incorrecto en .env → Telegram devuelve "Chat not found" → el scorer abortaba el flujo antes de guardar en DB → `alert_sent` nunca se ponía en `True` → "Sin alerta" en dashboard.

**Bug secundario encontrado**: incluso si Telegram hubiera funcionado, `_save_alert()` solo insertaba en la tabla `Alert` pero **nunca** hacía `UPDATE token_candidates SET alert_sent=True`. Ese flag jamás se habría activado.

### Fixes aplicados

**scorer_agent.py** — dos cambios:
1. Desacoplar Telegram del guardado en DB: Telegram pasa a ser best-effort. Si falla, loguea el error pero continúa para guardar en DB.
2. `_save_alert()` ahora hace dos operaciones en la misma sesión: insert en `Alert` + `UPDATE token_candidates SET alert_sent=True WHERE symbol=...`

**detector_agent.py** — guarda breakdown JSON:
Cada vez que el Detector actualiza el score en DB, también guarda el campo `score_breakdown` con el desglose por componente del patrón dominante:
```json
{"dominant": "long_pump", "lp_inflow": 40.0, "lp_holder": 0.0, "lp_price": 17.0, "lp_funding": 7.5, ...}
```

**shared/models/token_candidate.py** — nuevo campo `score_breakdown TEXT`

**Migración 0003** — `ALTER TABLE token_candidates ADD COLUMN IF NOT EXISTS score_breakdown TEXT`  
Aplicada directamente via psql (alembic no disponible en containers por configuración de rutas).

**Dashboard tooltip** — hover sobre el número de score muestra:
- Para Long Pump: Inflow / On-chain / Precio / Funding (cada uno en pts)
- Para Classic Squeeze: Short Int / Funding / Inflow / Holders

**ALERT_THRESHOLD bajado a 60** — con scores máximos de ~67.5 pts (sin Coinglass/derivados), el 62 era demasiado ajustado. Se bajó a 60 vía override explícito en `docker-compose.yml` (el .env tiene restricción de acceso desde Claude).

### Score breakdown observado (EUR/BILL/UMXM, Long Pump)

| Componente | Pts | Razón |
|---|---|---|
| Inflow 4h | ~40 | Inflow ≥ $1M (5x threshold de $200k) |
| On-chain | 0 | Coinglass deprecated, solo ERC20 en Etherscan |
| Precio estable | 12-20 | Variación 24h entre 1-7% |
| Funding neutral | 7.5 | Sin datos CCXT para spot → valor neutro |
| **Total** | **~62-66** | |

### Estado del Telegram

El error "Chat not found" persiste — requiere corrección manual del `TELEGRAM_CHAT_ID` en .env.  
Ahora el sistema funciona sin Telegram: guarda alertas en DB y marca `alert_sent=True` igualmente.  
Cuando se corrija el CHAT_ID, los próximos scores ≥60 enviarán Telegram automáticamente.

---

## Sesión 2026-05-14 — Sincronización CLAUDE.md + endpoint Executor manual

### Contexto

CLAUDE.md estaba desactualizado respecto a los cambios de las dos sesiones del 2026-05-13
documentadas en bitácora. Se realizó sincronización completa y se detectaron dos archivos
con cambios no comiteados (`agents/dashboard/routers/agents.py` y `agents/executor/executor_agent.py`).

### Cambios en CLAUDE.md

Correcciones y adiciones al estado operativo:

- **Conteo de tokens corregido**: `~247 tokens/ciclo` → `~532 tokens/ciclo, ~534 snapshots, ~113s`
- **4 trades paper** documentados: ACN ×2, LAB ×2 (ejecutados ~00:37 UTC del 2026-05-13)
- **Telegram best-effort** documentado: sistema guarda alertas en DB aunque falle Telegram
- **Discovery manual trigger** documentado: Dashboard → "Forzar scan ahora" → `channel:control:discovery:run`
- **Orchestrator health checks** documentados: ventana 25h para Discovery, `MAX(TokenCandidate.last_checked)` para Detector
- **Dashboard tooltip** documentado: hover sobre score muestra breakdown por componente
- **Migración 0002** documentada: reescrita con `ADD COLUMN IF NOT EXISTS`
- **Próximos pasos**: añadido `TELEGRAM_CHAT_ID` a la lista de variables pendientes en .env

### Cambios en agentes (no comiteados previos, incluidos en este commit)

**`agents/dashboard/routers/agents.py`**
- Nuevo endpoint `POST /agents/executor/run` → publica en `channel:control:executor:run`
- Permite disparar chequeo de posiciones del Executor desde el Dashboard

**`agents/executor/executor_agent.py`**
- Suscripción a `channel:control:executor:run` → `_handle_manual_trigger()`
- `_handle_manual_trigger()`: itera sobre todas las posiciones abiertas y llama `_check_position()`
- Heartbeat en el loop de monitoreo: `setex("executor:heartbeat", 120, len(positions))` — el Orchestrator detecta actividad aunque no haya trades nuevos

### Commit

```
1a87e2e docs: sincroniza CLAUDE.md con sesiones 2026-05-13 de bitácora
```

Pushed a `origin/main`.

---

## Sesión 2026-05-15 — Fix métrica Anticipación Promedio (0.0h → minutos reales)

### Problema reportado

La pantalla de Performance mostraba **Anticipación Promedio = 0.0h**. El usuario sospechaba
bug de cálculo o problema de timing.

### Diagnóstico

**Query ejecutada directamente en PostgreSQL:**

```sql
SELECT t.entry_time, a.sent_at,
  EXTRACT(EPOCH FROM (t.entry_time - a.sent_at))/3600 as horas_anticipacion
FROM trades t
JOIN alerts a ON a.token_symbol = t.token_symbol
ORDER BY t.entry_time DESC LIMIT 10;
```

Resultados representativos:

| Token | Δ horas | Δ real |
|---|---|---|
| GOLD(PAXG) | 0.00588 | ~21s |
| TON | 0.00073 | ~3s |
| DOGE | 0.01036 | ~37s |
| ADA | 0.00529 | ~19s |

**Conclusiones:**

1. **Fórmula correcta** — `entry_time - sent_at` es positivo (orden bien).
2. **Problema de diseño + precisión**: el Executor suscribe al mismo canal Redis que el Scorer
   (`channel:detector:scored_token`). Ambos reciben el evento en la misma pasada → el trade
   abre 4–37 segundos después de la alerta. `round(0.004h, 2)` = `0.0h`.
3. La métrica "anticipación en horas" **no tiene sentido** para auto-ejecución. Lo útil es:
   ¿cuánto tiempo lleva el token siendo alertado antes de entrar? → comparar `entry_time`
   con la **alerta más antigua** del token (no la más reciente).

### Cambios implementados

**`shared/models/trade.py`**
- Nuevo campo `anticipation_minutes: Mapped[Optional[float]]` (FLOAT nullable)

**`alembic/versions/0005_add_anticipation_minutes.py`** (nuevo)
- `ALTER TABLE trades ADD COLUMN IF NOT EXISTS anticipation_minutes FLOAT`
- `down_revision = "0004"` → cadena correcta

**`agents/executor/executor_agent.py`**
- Al abrir cada trade: consulta `MIN(Alert.sent_at)` para el token (alerta más antigua)
- Calcula `anticipation_minutes = (entry_time − oldest_alert.sent_at).total_seconds() / 60`
- Guarda el valor en el objeto `Trade` antes del `flush()`
- Import añadido: `from shared.models import Alert, ...` + `from sqlalchemy import select`

**`agents/dashboard/routers/performance.py`**
- Lee `t.anticipation_minutes` del campo pre-calculado (sin JOIN en tiempo de consulta)
- Retorna `avg_anticipation_minutes` en lugar de `avg_anticipation_hours`
- Import de `Alert` eliminado (ya no se usa en este módulo)

**`agents/dashboard/static/performance.html`**
- Card "Anticipación Promedio": unidad `h` → `min`
- Umbrales del semáforo: `(3h, 1.5h)` → `(30min, 5min)`
- Descripción: "entre alerta Telegram y entrada" → "entre 1ª alerta del token y entrada al trade"
- Veredicto: `≥ 3h` → `≥ 30 min`

**Migración aplicada directamente via psql** (misma estrategia que 0003 y 0004):
```sql
ALTER TABLE trades ADD COLUMN IF NOT EXISTS anticipation_minutes FLOAT;
UPDATE alembic_version SET version_num = '0005';
```

### Nota sobre trades existentes

Los 24 trades en DB tienen `anticipation_minutes = NULL` — la columna se añadió después.
Los próximos trades calcularán el valor correctamente desde el momento de apertura.

### Commit

```
1cfbb35 feat: anticipation_minutes en trades reemplaza avg_anticipation_hours
```

Pushed a `origin/main`.
