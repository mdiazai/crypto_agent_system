# CLAUDE.md — Crypto Agent System

## CONTEXTO DEL LAB — LEER PRIMERO
Este repo es un proyecto del 11Mkeys AI Lab y consume infraestructura compartida.
ANTES de trabajar: `cat /opt/11mkeys_lab/CLAUDE.md` (mapa completo: agentes, bots,
workflows, lecciones, restricciones del VPS, patrones establecidos).
Este archivo documenta SOLO lo específico de este proyecto — restricciones del VPS,
bots, workflows n8n y lecciones generales viven en el maestro, no acá.

Agentes compartidos que este proyecto consume: SmartDevops (diagnóstico), orchestrator
supervisor (monitoreo 60s), Finance Agent / Code Agent / Strategy Advisor (vía n8n).

## Descripción
Sistema multi-agente de detección y trading automático de "Criminal Pumps" en
criptomonedas de baja capitalización (paper trading). Historia completa de diseño y
construcción en `Bitacora.md` (líneas 1-828 — narrativa; desde la línea 829, sesiones
operativas fusionadas también en la Bitácora central del Lab, tag `[crypto_agent]`).

## Base de datos
- DB activa: `lab_11mkeys` (migrada desde `crypto_agent` el 2026-07-01 — ver maestro)
- Tablas propias: `token_candidates`, `alerts`, `trades`, `learning_logs`,
  `diagnostics_log`, `narrative_candidates`, `narrative_trades`
- Query segura (patrón general en el maestro): siempre `-d lab_11mkeys`, nunca `crypto_agent`

## Agentes Python (`agents/`)
| Agente | Función | Ciclo |
|---|---|---|
| discovery | Descubre tokens nuevos por volumen/narrativa | 1×/día 02:00 UTC |
| monitor | Precio, volumen, RSI, funding — CCXT | ~5 min |
| detector | Detección de señales on-chain (inflow, holders) | continuo |
| scorer | Score combinado, umbral de alerta | por ciclo de monitor |
| executor | Ejecución de trades paper, stop loss/take profit | continuo, heartbeat 30s |
| learner | Analiza trades cerrados, ajusta pesos | 1×/día |
| narrative | Narrative Swing Module — ver detalle abajo | 6h |
| smartdevops | Diagnóstico IA del sistema — ver maestro | 30 min |
| dashboard | UI web + API JWT | — |
| orchestrator | Supervisor liviano + market analysis — ver maestro | 60s |

## Umbrales y configuración (`shared/config/settings.py`)
Fuente única de verdad para thresholds — no duplicar valores acá, van desactualizándose.
Consultar el archivo directamente para valores actuales de `alert_threshold`,
`stop_loss_pct`, `take_profit_*_pct`, `inflow_threshold_usd`, etc.

## Build y deploy de agentes de este proyecto
Patrón general en el maestro. Específico de este repo:
- La mayoría de los agentes (`orchestrator`, `smartdevops`) NO están en
  `docker-compose.yml` — son containers standalone, recrear con
  `docker run --env-file` (nunca `restart` para picar cambios de `.env` — Lección 8).
- `orchestrator` hornea `alembic/` en su imagen (no bind-mount) — rebuildear con
  `--no-cache` después de CUALQUIER migración nueva, no solo cambios de `requirements.txt`
  (Lección 23).

## Narrative Swing Module
Vive temporalmente en `agents/narrative/` de este repo (compartiendo infra VPS con el
resto del Crypto Agent System). Se separará a `/opt/narrative_swing/` propio al cumplir
el gate de producción: 30 días de paper trading, 10 trades cerrados, win rate ≥55%,
profit factor ≥1.3. Progreso: comando `/gate` (PM Bot) o dashboard
`http://167.88.33.68:8001/static/narrative.html`.
Repo de desarrollo local: `C:\Users\Usuario\Desktop\narrative_swing` (Marce lo commitea
desde su máquina — ver CLAUDE.md propio de ese repo).

## Historial técnico detallado
Bug fixes específicos, decisiones de arquitectura con fecha, e iteraciones de cada
agente: ver `Bitacora.md` de este repo (narrativa completa) y la Bitácora central del
Lab (`/opt/11mkeys_lab/Bitacora.md`, tag `[crypto_agent]`, sesiones desde 2026-07-08).
