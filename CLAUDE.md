# CLAUDE.md — 11mkeys_lab

## Descripción
Stack de automatización del 11Mkeys IA Lab.
Orquesta el Crypto Agent System y futuros proyectos del lab
mediante n8n, bots de Telegram y la Claude API.

## Objetivo inmediato
Implementar Code Agent + Monkey Advisor sobre el VPS
donde ya corre el Crypto Agent System.

## VPS
- IP: 167.88.33.68
- SSH: ssh root@167.88.33.68
- Proyecto crypto: /opt/crypto_agent_system
- Proyecto lab: /opt/11mkeys_lab (a crear)

## Stack
n8n · Claude API · Telegram bots · bash scripts

## Documento de referencia
Ver: 11MKEYS_CODE_AGENT_SETUP_v2.md — contiene el plan
completo de 5 pasos con los workflows JSON listos para importar.

## Estado
- [x] PASO 0 — Crear bots de Telegram
- [x] PASO 1 — Agregar n8n al docker-compose.yml del crypto system
- [x] PASO 2 — Importar workflow Code Agent en n8n
- [x] PASO 3 — Importar workflow Monkey Advisor en n8n
- [x] PASO 4 — Configurar credenciales en n8n
- [x] PASO 5 — Registrar webhooks y probar

## Infraestructura n8n
- n8n corre en Docker en VPS Hostinger
- IP VPS: 167.88.33.68 — SSH: `ssh root@167.88.33.68`
- n8n path: `/opt/crypto_agent_system` (docker-compose + override)
- Dominio permanente: https://n8n.11mkeys.ai
- SSL: Let's Encrypt, vence 2026-08-30, renovación automática
- Nginx como reverse proxy a localhost:5678
- Puertos 80 y 443 abiertos en UFW

## Bots Telegram
- **Monkey Advisor:** `@MonkeyAdvisor_11Mkeys_bot`
  - Token: `8829243525:AAGvN7WJsGbM3Hfg0uDAPUog38yALBOghdQ`
  - Webhook: `https://n8n.11mkeys.ai/webhook/4ddb16b8-171d-4811-8da5-65e99b4ee153/webhook`
- **Code Agent:** `@ElevenMkeys_CodeAgent_bot`
  - Token: `8763657547:AAHBZoVejJnmYbg2n0gmOqQ48nLmqPjfvqM`
  - Webhook: `https://n8n.11mkeys.ai/webhook/c1a5e861-f106-4d7d-82e2-0be00cc13a7c/webhook`
  - allowed_updates: `message`, `callback_query`

## Code Agent Bot — Comandos disponibles
- `/fix_etherscan` — aplica fix Etherscan V2 con aprobación manual
- `/status` — estado contenedores Docker + count holder data
- `/logs` — últimos 20 logs del monitor (lee archivo JSON Docker directo)
- `/scores` — top 10 tokens por `detection_score` desde PostgreSQL
- `approve_deploy` — botón inline para aprobar deploy
- `reject_deploy` — botón inline para rechazar deploy

## Arquitectura n8n Code Agent (v7)
- Route Command → 3 outputs: `fix_etherscan`, `approve_deploy`, `reject_deploy`
- Ops Router → 3 outputs: `/status`, `/logs`, `/scores`
- Logs Check lee: `/var/lib/docker/containers/5ad364e864fa84e979d7271bf47c53854546ca7aad146c1e3bb52ea4d2886462/...-json.log`

## Workflows n8n
- **Monkey Advisor:** Telegram Trigger → Get System Context → Anthropic (nativo) → Send a text message
- **Code Agent:** Telegram Trigger → Route Command → Ops Router (arquitectura dual switch)

## Estado del sistema (2026-06-04)
- Monitor: 84 tokens activos, 83 publicados, 0 errores por ciclo
- `detection_score` todos en 25 (aplanado) — scorer pendiente de diagnóstico
- `holder_concentration_pct` activo vía Moralis ✅
- `agents/monitor/onchain_client.py`: `ETHERSCAN_BASE = https://api.etherscan.io/v2/api`
- ZINC/USDT warning recurrente — pendiente limpiar de `token_candidates`
- Pendiente: chainid en BscClient + OnchainClient fallback chain

## Reglas
- Nunca modificar /opt/crypto_agent_system directamente
  salvo los cambios específicos del PASO 1 (agregar n8n al compose)
- Cada paso requiere confirmación antes de continuar
- Actualizar este archivo al finalizar cada sesión