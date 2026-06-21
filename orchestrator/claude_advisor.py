"""
ClaudeAdvisor: consulta Claude cuando el mercado está en condiciones anómalas.

Usa la Claude API para obtener una recomendación sobre si ajustar
temporalmente los umbrales de detección. Incluye prompt caching en el
system prompt para reducir costos cuando se llama múltiples veces seguidas.

Rate: máximo 1 llamada por hora (gestionado via Redis TTL).
"""
import json
from typing import Optional
import structlog
import anthropic
import redis.asyncio as aioredis

from shared.config import settings
from .schemas import MarketContext, ThresholdAdvice

log = structlog.get_logger(__name__)

_ADVICE_COOLDOWN_KEY = "orchestrator:last_claude_advice"
_COOLDOWN_SECONDS = 3600

_SYSTEM_PROMPT = """Eres el asesor de riesgo de un sistema automatizado de trading de criptomonedas.
Tu función es analizar el contexto actual del mercado y recomendar si el sistema debe:
1. Subir el umbral de detección (más selectivo, menos trades)
2. Bajar el umbral (más agresivo, más trades)
3. Mantener el umbral actual

Criterios de decisión:
- Muchas señales simultáneas pueden indicar un entorno manipulado o un pump coordinado → subir umbral.
- Pocas señales con scores altos y mercado tranquilo → mantener o bajar ligeramente.
- Circuit breaker activo → recomendar SIEMPRE subir umbral hasta que se limpie.

Responde SOLO con un JSON válido con esta estructura exacta:
{
  "action": "raise_threshold" | "lower_threshold" | "keep_threshold",
  "new_threshold": <número 60-95 o null si keep>,
  "reason": "<explicación en 1-2 oraciones>",
  "confidence": <0.0-1.0>
}"""


class ClaudeAdvisor:
    def __init__(self) -> None:
        self._client = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key.get_secret_value(),
        )
        self._redis: Optional[aioredis.Redis] = None

    async def connect(self) -> None:
        self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)

    async def advise(self, context: MarketContext) -> Optional[ThresholdAdvice]:
        """
        Consulta a Claude solo si el mercado es anómalo y no se llamó en la última hora.
        Retorna ThresholdAdvice o None si no aplica.
        """
        if not context.is_anomalous:
            return None

        # Cooldown: no llamar más de 1 vez por hora
        if self._redis:
            if await self._redis.exists(_ADVICE_COOLDOWN_KEY):
                log.debug("claude_advisor.cooldown_active")
                return None

        prompt = _build_prompt(context)

        try:
            response = await self._client.messages.create(
                model=settings.claude_model,
                max_tokens=300,
                system=[
                    {
                        "type": "text",
                        "text": _SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": prompt}],
            )

            raw = response.content[0].text.strip()
            # Extraer JSON de la respuesta
            if "```" in raw:
                raw = raw.split("```")[1].replace("json", "").strip()

            data = json.loads(raw)
            advice = ThresholdAdvice(
                action=data.get("action", "keep_threshold"),
                new_threshold=data.get("new_threshold"),
                reason=data.get("reason", ""),
                confidence=float(data.get("confidence", 0.5)),
            )

            # Registrar cooldown
            if self._redis:
                await self._redis.setex(_ADVICE_COOLDOWN_KEY, _COOLDOWN_SECONDS, "1")

            log.info(
                "claude_advisor.advice_received",
                action=advice.action,
                new_threshold=advice.new_threshold,
                confidence=advice.confidence,
                reason=advice.reason,
                input_tokens=response.usage.input_tokens,
                cache_read=getattr(response.usage, "cache_read_input_tokens", 0),
            )
            return advice

        except json.JSONDecodeError:
            log.error("claude_advisor.invalid_json", raw=raw[:200])
            return None
        except anthropic.RateLimitError:
            log.warning("claude_advisor.rate_limit")
            return None
        except anthropic.APIError as e:
            log.error("claude_advisor.api_error", error=str(e))
            return None


def _build_prompt(ctx: MarketContext) -> str:
    return f"""CONTEXTO DE MERCADO ACTUAL

Señales detectadas (últimos 30 min): {ctx.signals_last_30m}
Score promedio de señales: {ctx.avg_score_last_30m:.1f}/100
Umbral de alerta actual: {settings.alert_threshold}
Anomalía detectada: {ctx.anomaly_reason}
Paper Trading activo: {settings.paper_trading}

¿Debo ajustar el umbral de detección? Responde con el JSON requerido."""
