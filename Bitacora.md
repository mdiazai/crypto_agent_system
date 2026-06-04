# Bitácora — 11Mkeys IA Lab

---

## Sesión 2026-05-30 / 2026-06-01 — Setup inicial + Monkey Advisor Bot

### Completado en esta sesión
- PASO 0: Creados bots de Telegram (11Mkeys Code Agent + Monkey Advisor 11Mkeys)
- PASO 1: n8n agregado al docker-compose.yml del crypto system. Fix aplicado: network `crypto_net` → `default`, y `N8N_SECURE_COOKIE=false` vía docker-compose.override.yml
- PASO 2: Workflow Code Agent importado en n8n
- PASO 3: Workflow Monkey Advisor importado en n8n
- PASO 4: Credenciales configuradas (11Mkeys Code Bot, Monkey Advisor Bot, Anthropic API)
- PASO 5: Webhooks registrados y sistema probado

### Problema resuelto — Monkey Advisor Bot

**Error inicial:** "JSON Body is not valid JSON" en el nodo final del workflow.

**Diagnóstico:**
- n8n ejecutaba versión cacheada del workflow con nodo HTTP Request viejo
- Webhook apuntaba a UUID antigua (`cf5dd669...`) ya inexistente
- URL base era túnel trycloudflare.com temporal (cambia en cada reinicio del contenedor)

**Fixes:**
1. Nodo Telegram nativo confirmado como correcto. Campo Text usa `$json.content[0].text` (output del nodo Anthropic nativo)
2. Instalado Nginx + Certbot en el VPS
3. Subdominio `n8n.11mkeys.ai` creado con registro A en GoDaddy → IP 167.88.33.68
4. Nginx configurado como reverse proxy a localhost:5678
5. SSL activado con Let's Encrypt — válido hasta 2026-08-30 (renovación automática)
6. Puertos 80 y 443 abiertos en UFW
7. Webhook actualizado a URL permanente

### Estado al cierre
- ✅ Monkey Advisor Bot respondiendo vía https://n8n.11mkeys.ai
- ✅ Infraestructura permanente — no requiere reconfiguración ante reinicios
- ⏳ Code Agent Bot — workflow importado, pendiente prueba con `/fix_etherscan`

---

## Sesión 2026-06-03

### Monkey Advisor Bot
- Fix webhook: URL permanente https://n8n.11mkeys.ai (Nginx + SSL Let's Encrypt)
- Registro A en GoDaddy: n8n.11mkeys.ai → 167.88.33.68
- Fix expresión Telegram: `$json.text` → `$json.content[0].text`
- Webhook Monkey Advisor: `/webhook/4ddb16b8-171d-4811-8da5-65e99b4ee153/webhook`

### Code Agent Workflow
- Corregido routing: 4 outputs limpios (fix_etherscan, status, approve_deploy, reject_deploy)
- Fix conexiones: Gen Diff → Ask Approval → Notify Fix Ready (secuencial)
- Fix conexiones: Verify → Notify Deploy OK → Notify Monkey Deploy Done (secuencial)
- Separados webhooks Monkey Advisor y Code Agent (tokens distintos)
- Code Agent webhook: `/webhook/3be05860-1ae8-403c-b660-4bde54ac85c6/webhook`

### Fix Etherscan V2
- `ETHERSCAN_V2_BASE` → `ETHERSCAN_BASE` en `onchain_client.py` (aplicado con sed)
- Monitor reiniciado: `holder_refresh.saved` activo vía Moralis
- 84 tokens procesados, 0 errores

### Infraestructura VPS
- Nginx + Certbot instalados
- SSL Let's Encrypt válido hasta 2026-08-30 (renovación automática)
- Puertos 80 y 443 abiertos en UFW
- Token Monkey Advisor: `8829243525`
- Token Code Agent: `8763657547`

### Pendientes
- Fix chainid BscClient + OnchainClient fallback (cortado por token limit)
- `/fix_coinglass` sin implementar en Code Agent
- Code Agent: cambiar estrategia → sed directo en lugar de enviar archivo completo a Claude

---
