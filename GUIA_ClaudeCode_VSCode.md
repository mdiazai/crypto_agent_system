# GUÍA DE USO — Claude Code en VS Code
### Cómo alimentar el sistema con el Master Prompt y el Blueprint

---

## PRE-REQUISITOS

Antes de empezar, asegúrate de tener instalado:

1. **Node.js 18+** (requerido por Claude Code)
   ```bash
   node --version   # debe mostrar v18 o superior
   ```

2. **Claude Code CLI**
   ```bash
   npm install -g @anthropic-ai/claude-code
   claude --version
   ```

3. **VS Code** con la extensión oficial de Claude Code (si usas la integración IDE)

4. **Python 3.11+** y **Docker Desktop** en tu máquina Windows

5. Tu **ANTHROPIC_API_KEY** lista

---

## PASO 1 — CREAR EL PROYECTO EN VS CODE

1. Abre VS Code
2. Crea una carpeta nueva: `crypto_agent_system`
3. Abre la terminal integrada (`` Ctrl+` ``)
4. Copia los dos archivos que descargaste a la raíz de esa carpeta:
   - `MASTER_PROMPT_CryptoAgent.md`
   - `BLUEPRINT_CryptoAgent.md`

```bash
# Estructura inicial que debes tener:
crypto_agent_system/
├── MASTER_PROMPT_CryptoAgent.md    ← El prompt completo
└── BLUEPRINT_CryptoAgent.md        ← El blueprint de investigación
```

---

## PASO 2 — INICIAR CLAUDE CODE

En la terminal integrada de VS Code, dentro de la carpeta del proyecto:

```bash
# Autenticarse (solo primera vez)
claude auth login

# Iniciar sesión interactiva de Claude Code
claude
```

Verás el prompt `>` de Claude Code listo para recibir instrucciones.

---

## PASO 3 — ALIMENTAR EL CONTEXTO

Claude Code puede leer archivos directamente. Usa estos comandos en orden:

### 3A — Cargar el Blueprint como contexto
```
> Por favor lee el archivo BLUEPRINT_CryptoAgent.md. Es el documento de investigación 
  y arquitectura del sistema que vamos a construir. Confirma que lo entendiste 
  resumiendo los 7 módulos principales.
```

### 3B — Cargar el Master Prompt
```
> Ahora lee el archivo MASTER_PROMPT_CryptoAgent.md. Este es el plan de construcción 
  completo. A partir de ahora, síguelo al pie de la letra fase por fase. 
  Comienza con la FASE 0.
```

---

## PASO 4 — FLUJO DE TRABAJO FASE A FASE

Después de que Claude Code complete cada fase, valida el resultado antes de avanzar:

### Comandos de navegación entre fases:

```bash
# Después de que termine la FASE 0:
> La FASE 0 está completa. Ahora procede con la FASE 1: crea los modelos 
  PostgreSQL y el Redis Message Bus según el MASTER_PROMPT.

# Después de FASE 1:
> Perfecto. Ahora construye la FASE 2: el Agente de Discovery con su 
  Cron Job diario y la integración a CoinGecko.

# Y así sucesivamente...
```

### Si necesitas que refactorize algo:
```bash
> El executor_agent.py no maneja correctamente los rate limits de Bitget. 
  Refactorízalo usando exponential backoff con máximo 3 reintentos.
```

---

## PASO 5 — COMANDOS ÚTILES DE CLAUDE CODE

```bash
# Ver qué archivos ha creado/modificado
> ¿Qué archivos has creado hasta ahora? Lista el árbol de directorios actual.

# Pedir tests
> Genera los tests unitarios para el score_engine.py

# Revisar un archivo específico
> Revisa el risk_manager.py y asegúrate de que el circuit breaker funciona 
  correctamente con asyncio.

# Pedir documentación
> Agrega docstrings a todos los métodos públicos de executor_agent.py

# Correr algo en terminal
> Ejecuta: docker-compose up -d postgres redis
  y verifica que los servicios estén funcionando
```

---

## PASO 6 — MODO ALTERNATIVO: ARCHIVO DE INSTRUCCIONES (CLAUDE.md)

Claude Code soporta un archivo especial `CLAUDE.md` en la raíz del proyecto que actúa como contexto persistente para toda la sesión. Crea este archivo:

```markdown
# CLAUDE.md — Instrucciones del Proyecto

## Contexto
Estamos construyendo un sistema multi-agente de detección de Criminal Pumps en criptomonedas.
Lee MASTER_PROMPT_CryptoAgent.md para el plan completo de construcción.
Lee BLUEPRINT_CryptoAgent.md para el contexto de negocio y arquitectura.

## Stack
Python 3.11, asyncio, FastAPI, Redis, PostgreSQL, CCXT, Claude API, Docker

## Reglas
- Todo el código debe ser async
- Paper trading habilitado por defecto (PAPER_TRADING=true)
- Nunca hardcodear credenciales
- Usar structlog para logging
- Type hints en todo el código

## Estado actual
[Claude Code actualiza esto automáticamente al avanzar fases]
```

Con `CLAUDE.md` en su lugar, Claude Code mantiene el contexto entre sesiones.

---

## PASO 7 — CONFIGURACIÓN DE VARIABLES DE ENTORNO

Cuando Claude Code genere el `.env.example`, copia y completa:

```bash
cp .env.example .env
```

Edita `.env` con tus claves reales:
```env
# IA
ANTHROPIC_API_KEY=sk-ant-...

# Exchanges (SOLO permisos de trading, nunca withdrawal)
MEXC_API_KEY=tu_clave_mexc
MEXC_SECRET=tu_secret_mexc
BITGET_API_KEY=tu_clave_bitget
BITGET_SECRET=tu_secret_bitget

# Telegram
TELEGRAM_BOT_TOKEN=tu_token_bot
TELEGRAM_CHAT_ID=tu_chat_id

# On-chain
GLASSNODE_API_KEY=tu_clave_glassnode
ETHERSCAN_API_KEY=tu_clave_etherscan

# CRÍTICO: Empieza siempre en Paper Trading
PAPER_TRADING=true
CAPITAL_TOTAL_USD=1000
MEXC_ALLOCATION_PCT=69
BITGET_ALLOCATION_PCT=31
```

---

## PASO 8 — LEVANTAR EL SISTEMA

```bash
# Levantar infraestructura (PostgreSQL + Redis)
docker-compose up -d postgres redis

# Verificar
docker-compose ps

# Ejecutar migraciones de base de datos
docker-compose run --rm orchestrator alembic upgrade head

# Levantar todos los agentes
docker-compose up -d

# Ver logs en tiempo real
docker-compose logs -f discovery monitor detector
```

---

## PASO 9 — DEPLOY EN VPS HOSTINGER

Una vez que el sistema funciona localmente:

```bash
# En tu VPS Hostinger (conectado via SSH)
git clone tu_repo /opt/crypto_agent_system
cd /opt/crypto_agent_system
cp .env.example .env
# Editar .env con claves de producción

# Levantar en producción
docker-compose -f docker-compose.yml up -d

# Monitorear
docker-compose logs -f
```

---

## TIPS PARA TRABAJAR CON CLAUDE CODE

1. **Sé específico**: En lugar de "mejora el discovery", di "el discovery_agent.py no maneja el caso donde CoinGecko devuelve 429 (rate limit). Agrega retry con backoff exponencial de 2^n segundos, máximo 5 intentos."

2. **Valida en fragmentos**: Pide que muestre el código antes de escribirlo a disco cuando no estés seguro del approach.

3. **Usa `/compact`** si la sesión se vuelve muy larga — resume el contexto sin perderlo.

4. **Mantén CLAUDE.md actualizado**: Pide a Claude Code que actualice el estado de las fases completadas en CLAUDE.md después de cada fase.

5. **Primero paper trading, siempre**: No cambies `PAPER_TRADING=false` hasta tener al menos 30 días de datos del ciclo de aprendizaje.

---

## ESTRUCTURA FINAL ESPERADA DEL PROYECTO

```
crypto_agent_system/
├── CLAUDE.md                   ← Contexto persistente para Claude Code
├── MASTER_PROMPT_CryptoAgent.md
├── BLUEPRINT_CryptoAgent.md
├── README.md
├── requirements.txt
├── .env.example
├── .env                        ← Nunca commitear a git
├── docker-compose.yml
├── alembic.ini
├── orchestrator/
│   ├── main.py
│   ├── agent_supervisor.py
│   ├── market_context.py
│   └── claude_advisor.py
├── agents/
│   ├── discovery/
│   ├── monitor/
│   ├── detector/
│   ├── scorer/
│   ├── executor/
│   ├── learner/
│   └── dashboard/
├── shared/
│   ├── models/
│   ├── redis_bus/
│   ├── config/
│   └── utils/
└── tests/
    ├── unit/
    └── integration/
```

---

*Guía de uso para el sistema crypto_agent_system | Versión 1.0 | Mayo 2026*
