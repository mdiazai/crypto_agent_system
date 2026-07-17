"""
Cliente CryptoPanic API (plan Growth) — noticias y sentiment por moneda.
Base URL y auth verificados en vivo: /api/growth/v2/posts/?auth_token=&currencies=

Cloudflare bloquea clientes HTTP sin User-Agent de navegador — imprescindible
fijarlo o todas las requests devuelven un 403 HTML en vez de JSON.
"""
from dataclasses import dataclass, field
from typing import Optional

import httpx
import structlog

from shared.config import settings
from shared.utils.retry import http_retry

log = structlog.get_logger(__name__)

_BASE = "https://cryptopanic.com/api/growth/v2/posts/"
_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) narrative-swing-agent/1.0"


@dataclass
class CryptoPanicNews:
    symbol: str
    positive_news_count: int = 0
    negative_news_count: int = 0
    avg_panic_score: Optional[float] = None
    top_headlines: list[str] = field(default_factory=list)


class CryptoPanicClient:
    def __init__(self) -> None:
        self._token = settings.cryptopanic_api_key.get_secret_value()

    @http_retry
    async def _get(self, symbol: str) -> Optional[dict]:
        async with httpx.AsyncClient(timeout=15.0, headers={"User-Agent": _USER_AGENT}) as client:
            resp = await client.get(_BASE, params={
                "auth_token": self._token,
                "currencies": symbol,
                "public": "true",
            })
            resp.raise_for_status()
            return resp.json()

    async def get_news(self, symbol: str) -> CryptoPanicNews:
        try:
            payload = await self._get(symbol)
        except Exception as e:
            log.warning("cryptopanic_client.error", symbol=symbol, error=str(e))
            return CryptoPanicNews(symbol=symbol)

        results = (payload or {}).get("results") or []
        if not results:
            return CryptoPanicNews(symbol=symbol)

        positive = 0
        negative = 0
        panic_scores: list[float] = []
        headlines: list[str] = []
        for post in results[:20]:
            votes = post.get("votes") or {}
            pos, neg = votes.get("positive", 0), votes.get("negative", 0)
            if pos > neg:
                positive += 1
            elif neg > pos:
                negative += 1
            score = post.get("panic_score")
            if score is not None:
                panic_scores.append(score)
            if len(headlines) < 3 and post.get("title"):
                headlines.append(post["title"])

        avg_panic = sum(panic_scores) / len(panic_scores) if panic_scores else None

        return CryptoPanicNews(
            symbol=symbol,
            positive_news_count=positive,
            negative_news_count=negative,
            avg_panic_score=avg_panic,
            top_headlines=headlines,
        )
