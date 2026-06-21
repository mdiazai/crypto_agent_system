# BLUEPRINT TÉCNICO — Sistema Automatizado de Detección de Criminal Pumps
### Documento de Investigación Compilado | Fuente: KManuS88 (YouTube) + Análisis NotebookLM

---

## 1. ORIGEN Y CASO DE ÉXITO

El sistema nació de un experimento: un bot simple construido con **Claude Code** para automatizar compra/venta en exchanges con el objetivo de acumular airdrops (criptomonedas gratis por usar una plataforma). Sin embargo, la estrategia de trading en sí resultó altamente rentable de forma inesperada: **convirtió $640 en $1,752 en 60-80 días** (ganancia de $1,112), operando de forma completamente autónoma durante días sin intervención humana.

Este éxito validó el concepto y llevó al desarrollo del sistema avanzado: el **Detector de Criminal Pumps**, que en su primer día de operación identificó correctamente tres tokens horas antes de sus subidas violentas:
- **COLLECT**: de $0.028 → $0.045
- **PROS**: de $0.67 → $1.90
- **PLAY**: de $0.06 → $0.09 (+50%)

**Advertencia del creador:** El creador enfatiza que 2-3 casos exitosos pueden ser suerte, y que el sistema necesita 7-30 días de datos para demostrar su efectividad real.

---

## 2. DEFINICIÓN DE "CRIMINAL PUMP"

Un "criminal pump" o "scam pump" es una manipulación extrema del mercado donde el precio de una criptomoneda experimenta subidas **violentas y artificiales**, por ejemplo:
- De $0.30 a $27 en pocas horas
- De $0.70 a $4.50 en minutos

Anteriormente, detectar estas oportunidades requería **10 horas diarias frente al monitor**, con el riesgo de perder el momento exacto por cualquier interrupción (cenar, tomar café). El sistema automatiza este proceso completamente.

---

## 3. ARQUITECTURA DE 7 MÓDULOS

### Módulo 1 — Motor de IA Principal
| Campo | Detalle |
|-------|---------|
| Función | Cerebro del sistema; traduce reglas manuales de trading en código automatizado |
| Herramienta usada | Claude Code (Claude API) |
| Recomendación técnica | API de Claude Sonnet para análisis heurístico y generación de código base |

### Módulo 2 — Discovery (Descubrimiento)
| Campo | Detalle |
|-------|---------|
| Función | Busca nuevos tokens candidatos en los exchanges |
| Frecuencia | Una vez al día (automático) |
| Lógica | Escanea TODOS los tokens; evalúa candidatos existentes; elimina los que no califican |
| Recomendación técnica | Cron Job en Python consumiendo APIs de CoinGecko/CoinMarketCap cada 24h |

### Módulo 3 — Monitor (Monitoreo)
| Campo | Detalle |
|-------|---------|
| Función | Revisa tokens pre-seleccionados para identificar el momento exacto de entrada |
| Frecuencia | Cada 5 minutos (automático) |
| Lógica | Chequea oportunidades basándose en reglas predefinidas |
| Recomendación técnica | WebSockets para precios en tiempo real + llamadas REST cada 5 min a APIs de exchanges |

### Módulo 4 — Lógica de Detección
| Campo | Detalle |
|-------|---------|
| Función | Identifica patrones de manipulación antes de que ocurran |
| Patrones | Long Pump (patrón alternativo) y Classic (basado en Short Squeeze) |
| Variables clave | Timeline de holders (concentración de tokens) + Inflow (ingreso masivo a exchange) |
| Recomendación técnica | Scripts Python analizando datos on-chain via Etherscan, Solscan o Glassnode |

### Módulo 5 — Sistema de Alerta y Puntuación
| Campo | Detalle |
|-------|---------|
| Función | Notifica al usuario con horas de anticipación cuando un token está por explotar |
| Datos enviados | Ticker, puntuación, tipo de patrón, precio actual |
| Anticipación demostrada | 5-6 horas antes del pump (ej: alertas desde las 9am) |
| Recomendación técnica | API de Telegram (BotFather) para notificaciones push inmediatas |

### Módulo 6 — Motor de Ejecución Automática
| Campo | Detalle |
|-------|---------|
| Función | Compra y vende automáticamente sin intervención manual |
| Distribución de capital | 69% en MEXC, 31% en Bitget (configurable; planea agregar más exchanges) |
| Recomendación técnica | APIs privadas de MEXC y Bitget via CCXT (Python/JS) con claves API restringidas a trading |

### Módulo 7 — Ciclo de Aprendizaje (Machine Learning)
| Campo | Detalle |
|-------|---------|
| Función | Registra operaciones y refina parámetros para mejorar resultados |
| Evaluación | Si entró bien / mal / tarde / muy anticipado |
| Tiempo mínimo | 7 días para primeros valores; 30 días para optimización real |
| Recomendación técnica | PostgreSQL o MongoDB para log de trades + modelo ML predictivo para ajustar pesos |

---

## 4. INTERFAZ DE USUARIO (DASHBOARD)

El dashboard actúa como centro de control visual del sistema:

- **Gráficos de compra/venta**: Muestra niveles automatizados con contexto visual del token
- **Panel de análisis de tokens**: Al clickear un token, muestra criterio activo (Long Pump o Classic), timeline de holders y gráfico de inflow
- **Panel de ejecución**: Input de capital total y controles de distribución porcentual por exchange. Al guardar, el sistema toma control automático
- **Indicadores de estado**: Muestra estado en tiempo real del módulo Discovery cuando está escaneando
- **Botones manuales de trigger**: Para forzar actualizaciones (aunque el sistema lo hace automático cada 5 min)
- **Panel de aprendizaje**: Historial de trades con calidad de entrada; requiere semanas de datos para mostrar valores significativos
- **Integración Telegram**: Canal externo de notificaciones push en tiempo real (complementario al dashboard web)
- **Acceso**: Usuario + contraseña (autenticación básica)

---

## 5. FILOSOFÍA DE MONETIZACIÓN

**Tres objetivos de negocio simultáneos:**

1. **Ganancia pasiva directa**: El bot opera autónomamente 24/7 capitalizando pumps
2. **Escalabilidad comunitaria**: Las señales del bot se integrarán en "Outliners" (academia cripto del creador) como valor para su comunidad
3. **Modelo replicable**: Demuestra que CUALQUIER profesional con trabajo digital puede automatizar el 80% de sus tareas con IA y monetizarlas (no solo criptos: diseño, arquitectura, marketing, etc.)

**Filosofía central**: La IA no es solo una herramienta técnica — es un multiplicador de valor para cualquier industria digital.

---

## 6. CRITERIOS TÉCNICOS DE DETECCIÓN

### Long Pump
- Patrón alternativo al Classic
- El dashboard muestra cuál de los dos patrones "suena más fuerte"
- Validado con datos de holder concentration + inflow

### Classic (Short Squeeze)
- Método "clásico" que los manipuladores suelen usar
- Basado en estrategia de short squeeze
- Identificado por: posiciones short elevadas + inflow masivo como activador del squeeze

### Variables On-Chain para ambos patrones:
- **Timeline de holders**: ¿Hay concentración de tokens en pocas wallets? ¿Cómo evolucionó en el tiempo?
- **Exchange Inflow**: ¿Está entrando una cantidad masiva de tokens a un exchange? → señal de "algo va a pasar"

---

## 7. STACK TÉCNICO RECOMENDADO (Ingeniería Inversa)

| Componente | Tecnología |
|-----------|------------|
| Motor IA | API de Claude Sonnet (o GPT-4o) |
| Scheduler diario | Cron Job en Python/Node.js |
| Monitoreo cada 5 min | WebSockets + REST (CCXT) |
| Datos on-chain | Etherscan, Solscan, Glassnode APIs |
| Alertas | Telegram Bot API (BotFather) |
| Ejecución | CCXT con APIs privadas de MEXC y Bitget |
| Almacenamiento | PostgreSQL o MongoDB |
| ML Ciclo Aprendizaje | scikit-learn o modelo predictivo customizado |

---

## 8. PROMPT BASE PARA LLM (Ingeniería Inversa)

```
"Eres un Arquitecto de Software y experto en Trading Algorítmico. 
Te entrego el siguiente blueprint técnico extraído de un caso de éxito. 
Quiero que escribas el código en Python, estructurado en microservicios, 
para construir este sistema desde cero. 

Empieza detallando:
1. La estructura de carpetas del proyecto
2. Las bibliotecas necesarias (como CCXT para interactuar con MEXC/Bitget)
3. El script principal para el 'Módulo de Descubrimiento' utilizando datos on-chain
4. Los criterios de detección para Long Pump y Classic Short Squeeze
5. La integración con Telegram para alertas

Stack preferido: Python 3.11 + asyncio + FastAPI + Redis + PostgreSQL"
```

---

## 9. MÉTRICAS DE ÉXITO DEL SISTEMA

| Métrica | Objetivo |
|---------|---------|
| Win Rate | > 60% de trades rentables |
| Avg. Entry Quality | Mayoría en "good" o "perfect" |
| Anticipación promedio | > 3 horas antes del pump |
| Drawdown máximo | < 15% del capital en cualquier día |
| Tiempo de respuesta | < 30 segundos desde señal hasta ejecución |
| Uptime del sistema | > 99% (bot nunca duerme) |

---

## 10. FUENTES ORIGINALES

- **Video YouTube**: https://www.youtube.com/watch?v=3dDKvKqtKUE (KManuS88)
- **Análisis NotebookLM**: 7 documentos de análisis profundo del sistema
- **Mind Map**: Estructura conceptual del AI Crypto Automation System
- **Blueprints técnicos**: Tabla de componentes y funciones del detector

---

*Documento compilado para uso en ingeniería inversa con Claude Code. Mayo 2026.*
