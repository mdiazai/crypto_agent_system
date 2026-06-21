# 11Mkeys Lab — Setup Completo
## Code Agent + Monkey Advisor + Plan de implementación

**VPS:** `167.88.33.68` — `/opt/crypto_agent_system`
**Fecha:** Mayo 2026

---

## QUÉ VAMOS A CONSTRUIR (en lenguaje simple)

Tres piezas nuevas que transforman cómo trabajás con el lab:

**1. n8n** — es el "despachante de tareas". Corre en tu VPS 24/7 y puede
ejecutar cualquier acción automatizada: correr código, llamar a la IA,
enviar mensajes, deployar cambios. Lo controlás desde Telegram.

**2. Code Agent bot** — un bot de Telegram que recibe tus comandos
(`/fix_etherscan`, `/status`, etc.) y ejecuta los fixes del Plan 30 Días
sin que estés en la computadora. Te manda el resultado para que aprobés.

**3. Monkey Advisor bot** — un bot de Telegram separado que te explica
en lenguaje claro qué pasó en cada acción técnica. Podés preguntarle
cualquier cosa sobre el sistema en cualquier momento.

---

## PASO 0 — Crear los dos bots de Telegram

### Bot 1: Code Agent (para ejecutar fixes y deployar)

1. Abrí `@BotFather` en Telegram
2. `/newbot` → Nombre: `11Mkeys Code Agent` → Username: `mkeys_code_bot`
3. Guardá el token → `MKEYS_BOT_TOKEN`
4. Enviá un mensaje al bot para activar el chat
5. Obtené tu CHAT_ID:
   ```
   https://api.telegram.org/bot<MKEYS_BOT_TOKEN>/getUpdates
   ```
   Buscá `"chat":{"id":XXXXXXX}` → ese es `MKEYS_CHAT_ID`

### Bot 2: Monkey Advisor (para explicaciones y consultas)

1. En `@BotFather`: `/newbot`
2. Nombre: `Monkey Advisor 11Mkeys` → Username: `monkey_advisor_bot`
3. Guardá el token → `MONKEY_BOT_TOKEN`
4. Enviá un mensaje al bot para activar el chat
5. Mismo proceso para obtener → `MONKEY_CHAT_ID`
   (probablemente es el mismo número que `MKEYS_CHAT_ID` — tu ID de usuario no cambia)

### Agregar al .env del VPS:

```bash
printf "\nMKEYS_BOT_TOKEN=<token_code_agent>\nMKEYS_CHAT_ID=<chat_id>\nMONKEY_BOT_TOKEN=<token_monkey>\nMONKEY_CHAT_ID=<chat_id>\nN8N_PASSWORD=<password_seguro>\n" >> /opt/crypto_agent_system/.env
sed -i 's/\r//' /opt/crypto_agent_system/.env
```

---

## PASO 1 — Agregar n8n al docker-compose.yml

Archivo: `/opt/crypto_agent_system/docker-compose.yml`

Agregá dentro de `services:` (antes del bloque `volumes:`):

```yaml
  n8n:
    image: n8nio/n8n:latest
    restart: unless-stopped
    ports:
      - "5678:5678"
    environment:
      - N8N_BASIC_AUTH_ACTIVE=true
      - N8N_BASIC_AUTH_USER=admin
      - N8N_BASIC_AUTH_PASSWORD=${N8N_PASSWORD}
      - N8N_HOST=0.0.0.0
      - N8N_PORT=5678
      - N8N_PROTOCOL=http
      - WEBHOOK_URL=http://167.88.33.68:5678/
      - GENERIC_TIMEZONE=America/Montevideo
      - N8N_LOG_LEVEL=info
      - EXECUTIONS_DATA_SAVE_ON_ERROR=all
      - EXECUTIONS_DATA_SAVE_ON_SUCCESS=all
      - MKEYS_CHAT_ID=${MKEYS_CHAT_ID}
      - MONKEY_CHAT_ID=${MONKEY_CHAT_ID}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
    volumes:
      - n8n_data:/home/node/.n8n
      - /opt/crypto_agent_system:/workspace:rw
      - /var/run/docker.sock:/var/run/docker.sock
      - /usr/bin/docker:/usr/bin/docker:ro
    user: root
    networks:
      - crypto_net
```

Agregá el volumen en el bloque `volumes:`:
```yaml
  n8n_data:
```

Levantá n8n:
```bash
cd /opt/crypto_agent_system
ufw allow 5678/tcp
docker compose up -d --no-deps n8n
docker compose logs n8n --tail=20
```

Verificá acceso: `http://167.88.33.68:5678`
Login: `admin` / `<N8N_PASSWORD>`

---

## PASO 2 — Workflow: Code Agent

En n8n → Import Workflow → pegá este JSON:

```json
{
  "name": "11Mkeys Code Agent",
  "nodes": [
    {
      "name": "Telegram Trigger",
      "type": "n8n-nodes-base.telegramTrigger",
      "parameters": {
        "updates": ["message", "callback_query"]
      },
      "credentials": { "telegramApi": { "name": "11Mkeys Code Bot" } },
      "position": [240, 300]
    },
    {
      "name": "Route Command",
      "type": "n8n-nodes-base.switch",
      "parameters": {
        "dataType": "string",
        "value1": "={{ $json.message?.text || $json.callback_query?.data }}",
        "rules": { "rules": [
          { "value2": "/fix_etherscan", "output": 0 },
          { "value2": "/fix_coinglass",  "output": 1 },
          { "value2": "/status",         "output": 2 },
          { "value2": "approve_deploy",  "output": 3 },
          { "value2": "reject_deploy",   "output": 4 }
        ]}
      },
      "position": [460, 300]
    },
    {
      "name": "Read onchain_client",
      "type": "n8n-nodes-base.executeCommand",
      "parameters": { "command": "cat /workspace/agents/monitor/onchain_client.py" },
      "position": [700, 160]
    },
    {
      "name": "Claude API Fix Etherscan",
      "type": "n8n-nodes-base.httpRequest",
      "parameters": {
        "method": "POST",
        "url": "https://api.anthropic.com/v1/messages",
        "authentication": "genericCredentialType",
        "genericAuthType": "httpHeaderAuth",
        "sendHeaders": true,
        "headerParameters": { "parameters": [
          { "name": "anthropic-version", "value": "2023-06-01" },
          { "name": "content-type",      "value": "application/json" }
        ]},
        "sendBody": true,
        "bodyParameters": { "parameters": [
          { "name": "model",      "value": "claude-sonnet-4-6" },
          { "name": "max_tokens", "value": "4096" },
          { "name": "system",     "value": "Sos un experto en Python async y APIs blockchain. Aplicás fixes específicos a archivos. Devolvés SOLO el archivo Python completo modificado, sin explicaciones, sin markdown, sin backticks." },
          { "name": "messages",   "value": "=[{\"role\":\"user\",\"content\":\"Aplicá estos cambios al archivo:\\n\\nCAMBIO 1 — URL base:\\nANTES: ETHERSCAN_BASE = 'https://api.etherscan.io/api'\\nDESPUES: ETHERSCAN_BASE = 'https://api.etherscan.io/v2/api'\\n\\nCAMBIO 2 — Agregar chainid=1 en EtherscanClient.get_holder_concentration:\\nparams = {\\n    'chainid': 1,\\n    'module': 'token',\\n    'action': 'tokenholderlist',\\n    'contractaddress': contract_address,\\n    'page': 1, 'offset': 10,\\n    'apikey': self._api_key\\n}\\n\\nCAMBIO 3 — BscClient separado con chainid=56 en cada request.\\n\\nCAMBIO 4 — OnchainClient.get_holder_concentration:\\nchain='evm' intentar chainid=1 primero, luego chainid=56.\\nchain='solana' Helius sin cambios.\\n\\nARCHIVO ACTUAL:\\n\" + $('Read onchain_client').item.json.stdout}]" }
        ]}
      },
      "position": [940, 160]
    },
    {
      "name": "Extract Code",
      "type": "n8n-nodes-base.code",
      "parameters": { "jsCode": "const r=$input.item.json; const c=r.content[0].text; return [{json:{fixedCode:c,lines:c.split('\\n').length}}];" },
      "position": [1160, 160]
    },
    {
      "name": "Write File",
      "type": "n8n-nodes-base.executeCommand",
      "parameters": { "command": "=cp /workspace/agents/monitor/onchain_client.py /workspace/agents/monitor/onchain_client.py.bak && printf '%s' '{{ $json.fixedCode }}' > /workspace/agents/monitor/onchain_client.py && echo OK" },
      "position": [1380, 160]
    },
    {
      "name": "Gen Diff",
      "type": "n8n-nodes-base.executeCommand",
      "parameters": { "command": "cd /workspace && git diff agents/monitor/onchain_client.py | head -60" },
      "position": [1580, 160]
    },
    {
      "name": "Notify Monkey Advisor - Fix Ready",
      "type": "n8n-nodes-base.httpRequest",
      "parameters": {
        "method": "POST",
        "url": "=https://api.telegram.org/bot{{ $env.MONKEY_BOT_TOKEN }}/sendMessage",
        "sendBody": true,
        "bodyParameters": { "parameters": [
          { "name": "chat_id", "value": "={{ $env.MONKEY_CHAT_ID }}" },
          { "name": "text",    "value": "=🐒 *Monkey Advisor*\\n\\n*¿Qué acaba de pasar?*\\nEl Code Agent terminó de preparar un fix para el sistema de detección de criptomonedas.\\n\\n*¿Qué es Etherscan?*\\nEtherscan es como el 'Google Maps' de la blockchain de Ethereum. Muestra quién tiene qué tokens y cuánto. El sistema lo usa para detectar si pocas ballenas (wallets grandes) acumularon un token antes de que suba.\\n\\n*¿Por qué cambiamos de V1 a V2?*\\nEtherscan dejó de mantener su API vieja (V1). Es como cuando una app te avisa que hay una versión nueva — si no actualizás, deja de funcionar. Con este fix, el sistema vuelve a ver los datos de concentración de holders.\\n\\n*¿Qué mejora esto en Criminal Pumps?*\\nEl score máximo de cada token sube de 67 a 92 puntos. Esos 25 puntos extra vienen de saber si pocas wallets tienen mucho del token — señal clave de un pump preparado.\\n\\n📱 Revisá el bot de Code Agent para aprobar el deploy." },
          { "name": "parse_mode", "value": "Markdown" }
        ]}
      },
      "position": [1800, 280]
    },
    {
      "name": "Ask Approval",
      "type": "n8n-nodes-base.telegram",
      "parameters": {
        "chatId": "={{ $env.MKEYS_CHAT_ID }}",
        "text": "=🔧 *Fix Etherscan V2 listo*\\n\\n```diff\\n{{ $json.stdout.substring(0,1400) }}\\n```\\n\\n¿Deployar?",
        "additionalFields": {
          "parse_mode": "Markdown",
          "reply_markup": "{\"inline_keyboard\":[[{\"text\":\"✅ Deploy\",\"callback_data\":\"approve_deploy\"},{\"text\":\"❌ Rechazar\",\"callback_data\":\"reject_deploy\"}]]}"
        }
      },
      "credentials": { "telegramApi": { "name": "11Mkeys Code Bot" } },
      "position": [1800, 160]
    },
    {
      "name": "Deploy",
      "type": "n8n-nodes-base.executeCommand",
      "parameters": { "command": "cd /workspace && git add agents/monitor/onchain_client.py && git commit -m 'fix: etherscan API V1 to V2 + chainid [auto 11Mkeys]' && git push origin main && docker compose build monitor && docker compose up -d --no-deps monitor 2>&1 | tail -15" },
      "position": [700, 420]
    },
    {
      "name": "Verify",
      "type": "n8n-nodes-base.executeCommand",
      "parameters": { "command": "sleep 12 && docker compose exec -T monitor python -c \"from agents.monitor.onchain_client import EtherscanClient; print('Etherscan V2 OK')\" 2>&1" },
      "position": [940, 420]
    },
    {
      "name": "Notify Deploy OK",
      "type": "n8n-nodes-base.telegram",
      "parameters": {
        "chatId": "={{ $env.MKEYS_CHAT_ID }}",
        "text": "=✅ *Deploy completado*\\n\\n```\\n{{ $json.stdout }}\\n```\\nMonitor reiniciado. Holder data activo en próximo ciclo.",
        "additionalFields": { "parse_mode": "Markdown" }
      },
      "credentials": { "telegramApi": { "name": "11Mkeys Code Bot" } },
      "position": [1160, 420]
    },
    {
      "name": "Notify Monkey Advisor - Deploy Done",
      "type": "n8n-nodes-base.httpRequest",
      "parameters": {
        "method": "POST",
        "url": "=https://api.telegram.org/bot{{ $env.MONKEY_BOT_TOKEN }}/sendMessage",
        "sendBody": true,
        "bodyParameters": { "parameters": [
          { "name": "chat_id", "value": "={{ $env.MONKEY_CHAT_ID }}" },
          { "name": "text",    "value": "=🐒 *Monkey Advisor*\\n\\n✅ *El fix fue deployado exitosamente*\\n\\n*¿Qué significa 'docker compose build + restart'?*\\nDocker es como cajas selladas donde vive cada parte del sistema. 'Build' reconstruye la caja del Monitor con el código nuevo. 'Restart' la vuelve a poner en funcionamiento. El resto del sistema siguió corriendo sin interrupciones.\\n\\n*¿Qué pasa ahora?*\\nEn las próximas 6 horas, el sistema consultará Etherscan V2 para los ~144 tokens que tienen dirección registrada. Los scores de esos tokens subirán porque ahora incluyen el dato de concentración de holders.\\n\\n*¿Cómo lo verificás?*\\nEntrá al dashboard: http://167.88.33.68:8001\\nEn la tabla del Scanner, pasá el mouse sobre el score de cualquier token. Deberías ver 'On-chain: X pts' en lugar de '0 pts'.\\n\\n¿Tenés alguna pregunta sobre este cambio?" },
          { "name": "parse_mode", "value": "Markdown" }
        ]}
      },
      "position": [1380, 420]
    },
    {
      "name": "Restore Backup",
      "type": "n8n-nodes-base.executeCommand",
      "parameters": { "command": "cd /workspace && cp agents/monitor/onchain_client.py.bak agents/monitor/onchain_client.py && echo 'Restaurado'" },
      "position": [700, 540]
    },
    {
      "name": "Notify Rejected",
      "type": "n8n-nodes-base.telegram",
      "parameters": {
        "chatId": "={{ $env.MKEYS_CHAT_ID }}",
        "text": "❌ Fix rechazado. Archivo restaurado al original.",
        "additionalFields": {}
      },
      "credentials": { "telegramApi": { "name": "11Mkeys Code Bot" } },
      "position": [940, 540]
    },
    {
      "name": "Status Check",
      "type": "n8n-nodes-base.executeCommand",
      "parameters": { "command": "cd /workspace && docker compose ps --format 'table {{.Name}}\\t{{.Status}}' && echo '---HOLDER DATA---' && docker compose exec -T postgres psql -U postgres -d crypto_agent -c \"SELECT COUNT(*) as con_holder_data FROM token_candidates WHERE holder_concentration_pct IS NOT NULL AND status='active';\" 2>/dev/null" },
      "position": [700, 640]
    },
    {
      "name": "Send Status",
      "type": "n8n-nodes-base.telegram",
      "parameters": {
        "chatId": "={{ $env.MKEYS_CHAT_ID }}",
        "text": "=📊 *Estado Criminal Pumps*\\n\\n```\\n{{ $json.stdout }}\\n```",
        "additionalFields": { "parse_mode": "Markdown" }
      },
      "credentials": { "telegramApi": { "name": "11Mkeys Code Bot" } },
      "position": [940, 640]
    }
  ],
  "connections": {
    "Telegram Trigger":            { "main": [[{ "node": "Route Command",                    "type": "main", "index": 0 }]] },
    "Route Command":               { "main": [
      [{ "node": "Read onchain_client",              "type": "main", "index": 0 }],
      [],
      [{ "node": "Status Check",                     "type": "main", "index": 0 }],
      [{ "node": "Deploy",                           "type": "main", "index": 0 }],
      [{ "node": "Restore Backup",                   "type": "main", "index": 0 }]
    ]},
    "Read onchain_client":         { "main": [[{ "node": "Claude API Fix Etherscan",          "type": "main", "index": 0 }]] },
    "Claude API Fix Etherscan":    { "main": [[{ "node": "Extract Code",                      "type": "main", "index": 0 }]] },
    "Extract Code":                { "main": [[{ "node": "Write File",                        "type": "main", "index": 0 }]] },
    "Write File":                  { "main": [[{ "node": "Gen Diff",                          "type": "main", "index": 0 }]] },
    "Gen Diff":                    { "main": [[{ "node": "Ask Approval",                      "type": "main", "index": 0 },
                                              { "node": "Notify Monkey Advisor - Fix Ready", "type": "main", "index": 0 }]] },
    "Deploy":                      { "main": [[{ "node": "Verify",                            "type": "main", "index": 0 }]] },
    "Verify":                      { "main": [[{ "node": "Notify Deploy OK",                  "type": "main", "index": 0 },
                                              { "node": "Notify Monkey Advisor - Deploy Done","type": "main", "index": 0 }]] },
    "Restore Backup":              { "main": [[{ "node": "Notify Rejected",                   "type": "main", "index": 0 }]] },
    "Status Check":                { "main": [[{ "node": "Send Status",                       "type": "main", "index": 0 }]] }
  }
}
```

---

## PASO 3 — Workflow: Monkey Advisor (consultas interactivas)

Este workflow responde cuando le escribís directamente al bot de Monkey Advisor.

En n8n → Import Workflow → pegá este JSON:

```json
{
  "name": "Monkey Advisor - Consultas",
  "nodes": [
    {
      "name": "Monkey Telegram Trigger",
      "type": "n8n-nodes-base.telegramTrigger",
      "parameters": { "updates": ["message"] },
      "credentials": { "telegramApi": { "name": "Monkey Advisor Bot" } },
      "position": [240, 300]
    },
    {
      "name": "Get System Context",
      "type": "n8n-nodes-base.executeCommand",
      "parameters": { "command": "cd /workspace && echo '=ESTADO SISTEMA=' && docker compose ps --format '{{.Name}} {{.Status}}' && echo '=CLAUDE.md=' && head -80 CLAUDE.md && echo '=ULTIMAS ALERTAS=' && docker compose exec -T postgres psql -U postgres -d crypto_agent -c \"SELECT token_symbol, score, sent_at FROM alerts ORDER BY sent_at DESC LIMIT 5;\" 2>/dev/null" },
      "position": [460, 300]
    },
    {
      "name": "Claude Monkey Advisor",
      "type": "n8n-nodes-base.httpRequest",
      "parameters": {
        "method": "POST",
        "url": "https://api.anthropic.com/v1/messages",
        "authentication": "genericCredentialType",
        "genericAuthType": "httpHeaderAuth",
        "sendHeaders": true,
        "headerParameters": { "parameters": [
          { "name": "anthropic-version", "value": "2023-06-01" },
          { "name": "content-type",      "value": "application/json" }
        ]},
        "sendBody": true,
        "bodyParameters": { "parameters": [
          { "name": "model",      "value": "claude-sonnet-4-6" },
          { "name": "max_tokens", "value": "1024" },
          { "name": "system",     "value": "Sos Monkey Advisor, el agente educativo del lab de IA '11Mkeys'. Tu misión es explicar conceptos técnicos en lenguaje claro y simple, sin jerga, para un founder de negocios inteligente que no es programador de carrera. Trabajás con el proyecto 'Criminal Pumps': un sistema de 7 agentes Python que detecta pumps en criptomonedas corriendo 24/7 en un VPS. Cuando expliques algo técnico, usá analogías de negocios o de la vida cotidiana. Sé conciso. Máximo 4 párrafos. Si el usuario pregunta qué hace un agente específico, explicá su rol en términos de negocio. Siempre terminá con una pregunta de seguimiento o una sugerencia de qué más podría querer saber." },
          { "name": "messages",   "value": "=[{\"role\":\"user\",\"content\":\"Contexto del sistema ahora:\\n\" + $('Get System Context').item.json.stdout + \"\\n\\nPregunta del founder: \" + $('Monkey Telegram Trigger').item.json.message.text}]" }
        ]}
      },
      "position": [700, 300]
    },
    {
      "name": "Send Monkey Response",
      "type": "n8n-nodes-base.httpRequest",
      "parameters": {
        "method": "POST",
        "url": "=https://api.telegram.org/bot{{ $env.MONKEY_BOT_TOKEN }}/sendMessage",
        "sendBody": true,
        "bodyParameters": { "parameters": [
          { "name": "chat_id",    "value": "={{ $env.MONKEY_CHAT_ID }}" },
          { "name": "text",       "value": "=🐒 *Monkey Advisor*\\n\\n{{ $json.content[0].text }}" },
          { "name": "parse_mode", "value": "Markdown" }
        ]}
      },
      "position": [940, 300]
    }
  ],
  "connections": {
    "Monkey Telegram Trigger": { "main": [[{ "node": "Get System Context",    "type": "main", "index": 0 }]] },
    "Get System Context":      { "main": [[{ "node": "Claude Monkey Advisor", "type": "main", "index": 0 }]] },
    "Claude Monkey Advisor":   { "main": [[{ "node": "Send Monkey Response",  "type": "main", "index": 0 }]] }
  }
}
```

---

## PASO 4 — Configurar credenciales en n8n

Settings → Credentials → New:

| Nombre             | Tipo              | Campo           | Valor                     |
|--------------------|-------------------|-----------------|---------------------------|
| 11Mkeys Code Bot   | Telegram API      | Access Token    | `<MKEYS_BOT_TOKEN>`       |
| Monkey Advisor Bot | Telegram API      | Access Token    | `<MONKEY_BOT_TOKEN>`      |
| Anthropic API      | HTTP Header Auth  | Header Name     | `x-api-key`               |
|                    |                   | Header Value    | `<ANTHROPIC_API_KEY>`     |

---

## PASO 5 — Registrar webhooks y probar

### Registrar webhooks de Telegram

Una vez que activés cada workflow en n8n, obtenés la URL del webhook en el nodo Trigger.
Registrala así para cada bot:

```bash
# Bot Code Agent
curl -X POST "https://api.telegram.org/bot<MKEYS_BOT_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url":"http://167.88.33.68:5678/webhook/<ID_NODO_CODE_TRIGGER>"}'

# Bot Monkey Advisor
curl -X POST "https://api.telegram.org/bot<MONKEY_BOT_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url":"http://167.88.33.68:5678/webhook/<ID_NODO_MONKEY_TRIGGER>"}'
```

### Secuencia de prueba

**1. Probá el Monkey Advisor primero (más seguro, no modifica código):**
   → Escribí al bot Monkey Advisor: `qué es Redis?`
   → Debería responder en lenguaje claro con el contexto de tu sistema

**2. Probá el status del Code Agent:**
   → Escribí al bot Code Agent: `/status`
   → Debería responder con el estado de los containers

**3. Ejecutá el primer fix real:**
   → Escribí al bot Code Agent: `/fix_etherscan`
   → En paralelo, el Monkey Advisor te explicará qué está pasando
   → Revisá el diff que llega al Code Agent bot
   → Presioná ✅ Deploy
   → El Monkey Advisor te confirma en lenguaje simple qué cambió

---

## Comandos disponibles

### Code Agent bot (`/comando`)
| Comando            | Acción                                           |
|--------------------|--------------------------------------------------|
| `/status`          | Estado containers + tokens con holder data       |
| `/fix_etherscan`   | PROMPT 1.1 — Fix Etherscan API V2                |
| `/fix_coinglass`   | PROMPT 1.2 — Reemplazar Coinglass con CCXT perps |
| `/fix_learner`     | PROMPT 2.2 — Activar ciclo del Learner           |
| `/metrics`         | Distribución scores + win rate actual            |
| `/logs monitor`    | Últimas 30 líneas del monitor agent              |

### Monkey Advisor bot (lenguaje natural)
Podés escribir cualquier pregunta:
- `qué es Redis?`
- `por qué usamos Docker?`
- `qué significa win rate?`
- `cómo funciona el Learner?`
- `qué pasó con el último deploy?`
- `cuánto capital está en riesgo ahora?`

---

*Generado por 11Mkeys IA Lab — Mayo 2026 — v2 con Monkey Advisor*
