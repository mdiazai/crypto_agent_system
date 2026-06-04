"""
Validación contextual con Claude API para tokens con score >= LLM_VALIDATION_THRESHOLD.

Usa prompt caching en el system prompt para reducir costos cuando se validan
múltiples tokens en el mismo ciclo.
"""
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional

import anthropic
import structlog

from shared.config import settings
from .schemas import ScoredToken

log = structlog.get_logger(__name__)

_SYSTEM_PROMPT = """Eres un analista experto en manipulación de mercados de criptomonedas, \
especializado en detectar "criminal pumps": movimientos de precio artificialmente inducidos \
por actores con información privilegiada o capital suficiente para mover mercados pequeños.

Tu rol es validar si una señal detectada algorítmicamente es genuina o un falso positivo, \
y explicar en lenguaje claro por qué este token específico podría experimentar una subida \
violenta en las próximas horas.

Reglas de análisis:
- Sé conciso: máximo 3 oraciones.
- Si los datos son insuficientes, dilo claramente.
- Usa lenguaje directo, sin eufemismos.
- NO hagas recomendaciones de inversión. Solo analiza el patrón detectado.
- Responde SIEMPRE en español."""

# Cache en memoria para evitar llamar Claude dos veces por el mismo token en < 1h
_validation_cache: dict[str, tuple[datetime, str]] = {}
_CACHE_TTL = timedelta(hours=1)


class ClaudeValidator:
    def __init__(self) -> None:
        self._client = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key.get_secret_value(),
        )

    async def validate(self, scored: ScoredToken) -> Optional[str]:
        """
        Retorna análisis en lenguaje natural del token, o None si hay error.
        Cachea el resultado por 1 hora por símbolo.
        """
        # Check cache
        cached = _validation_cache.get(scored.symbol)
        if cached:
            ts, analysis = cached
            if datetime.now(timezone.utc) - ts < _CACHE_TTL:
                log.debug("claude_validator.cache_hit", symbol=scored.symbol)
                return analysis

        prompt = _build_prompt(scored)

        try:
            response = await self._client.messages.create(
                model=settings.claude_model,
                max_tokens=400,
                system=[
                    {
                        "type": "text",
                        "text": _SYSTEM_PROMPT,
                        # Cache el system prompt — se reutiliza en cada llamada del ciclo
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": prompt}],
            )

            analysis = response.content[0].text.strip()
            _validation_cache[scored.symbol] = (datetime.now(timezone.utc), analysis)

            log.info(
                "claude_validator.validated",
                symbol=scored.symbol,
                score=scored.composite_score,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                cache_read=getattr(response.usage, "cache_read_input_tokens", 0),
            )
            return analysis

        except anthropic.RateLimitError:
            log.warning("claude_validator.rate_limit", symbol=scored.symbol)
            await asyncio.sleep(5)
            return None
        except anthropic.APIError as e:
            log.error("claude_validator.api_error", symbol=scored.symbol, error=str(e))
            return None


def _build_prompt(scored: ScoredToken) -> str:
    lp = scored.long_pump
    cl = scored.classic_squeeze

    inflow_str = f"${scored.inflow_4h_usd:,.0f}" if scored.inflow_4h_usd else "N/D"
    holder_str = f"{scored.holder_top10_pct:.1f}%" if scored.holder_top10_pct else "N/D"
    volume_str = f"${scored.volume_24h_usd:,.0f}" if scored.volume_24h_usd else "N/D"
    funding_str = f"{scored.funding_rate:.4f}%" if scored.funding_rate is not None else "N/D"

    return f"""SEÑAL DETECTADA — Validación requerida

Token: ${scored.symbol}
Exchange: {scored.exchange}
Precio actual: ${scored.current_price:.6f}
Volumen 24h: {volume_str}

SCORES ALGORÍTMICOS:
- Composite Score: {scored.composite_score:.1f}/100
- Patrón dominante: {scored.dominant_pattern.replace("_", " ").title()}
- Long Pump Score: {lp.score:.1f}/100
  · Inflow signal: {lp.inflow_signal:.1f} pts
  · Holder concentration: {lp.holder_signal:.1f} pts
  · Price stability: {lp.price_stability_signal:.1f} pts
  · Short pressure: {lp.funding_rate_signal:.1f} pts
- Classic Squeeze Score: {cl.score:.1f}/100
  · Short interest: {cl.short_interest_signal:.1f} pts
  · Funding rate: {cl.funding_rate_signal:.1f} pts
  · Inflow activator: {cl.inflow_signal:.1f} pts
  · Strong holders: {cl.holder_signal:.1f} pts

DATOS DE MERCADO:
- Inflow 4h hacia exchanges: {inflow_str}
- Concentración top-10 holders: {holder_str}
- Funding rate (futuros): {funding_str}

¿Es esta señal genuina? Explica brevemente el mecanismo de pump más probable."""
