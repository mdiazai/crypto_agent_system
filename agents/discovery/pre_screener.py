import structlog
from .schemas import TokenData

log = structlog.get_logger(__name__)

# Configurable defaults — zona de pumps óptima según el blueprint
MARKET_CAP_MIN_USD = 5_000_000
MARKET_CAP_MAX_USD = 500_000_000
VOLUME_TO_MCAP_RATIO_MIN = 0.03   # al menos 3% de mcap en volumen diario
TOKEN_AGE_MAX_DAYS = 730          # tokens con menos de 2 años (más volátiles)
PRICE_CHANGE_MAX_24H_PCT = 50     # evitar tokens ya en pump activo

# Filtros por volumen cuando no hay datos de CoinGecko
VOLUME_MIN_USD_FALLBACK = 100_000      # $100k mínimo diario (evita tokens muertos)
VOLUME_MAX_USD_FALLBACK = 100_000_000  # $100M máximo (gigacaps quedan fuera)


class PreScreener:
    def __init__(
        self,
        mcap_min: float = MARKET_CAP_MIN_USD,
        mcap_max: float = MARKET_CAP_MAX_USD,
        volume_ratio_min: float = VOLUME_TO_MCAP_RATIO_MIN,
        age_max_days: int = TOKEN_AGE_MAX_DAYS,
        price_change_max: float = PRICE_CHANGE_MAX_24H_PCT,
        blacklist: set[str] | None = None,
    ) -> None:
        self.mcap_min = mcap_min
        self.mcap_max = mcap_max
        self.volume_ratio_min = volume_ratio_min
        self.age_max_days = age_max_days
        self.price_change_max = price_change_max
        self.blacklist: set[str] = blacklist or set()

    def screen(self, tokens: list[TokenData]) -> tuple[list[TokenData], dict[str, str]]:
        passing: list[TokenData] = []
        rejected: dict[str, str] = {}

        for t in tokens:
            reason = self._reject_reason(t)
            if reason:
                rejected[t.symbol] = reason
            else:
                passing.append(t)

        log.info(
            "pre_screener.done",
            total=len(tokens),
            passing=len(passing),
            rejected=len(rejected),
        )
        return passing, rejected

    def _reject_reason(self, t: TokenData) -> str | None:
        if t.symbol in self.blacklist:
            return "blacklist"

        # Modo CoinGecko: usar market cap y ratio de volumen
        if t.market_cap_usd is not None:
            if t.market_cap_usd < self.mcap_min:
                return f"mcap_too_low:{t.market_cap_usd:.0f}"
            if t.market_cap_usd > self.mcap_max:
                return f"mcap_too_high:{t.market_cap_usd:.0f}"
            if t.volume_to_mcap_ratio is not None and t.volume_to_mcap_ratio < self.volume_ratio_min:
                return f"low_volume_ratio:{t.volume_to_mcap_ratio:.4f}"
        else:
            # Modo fallback (solo datos de exchange): filtrar por volumen diario
            vol = t.volume_24h_usd or 0.0
            if vol < VOLUME_MIN_USD_FALLBACK:
                return f"volume_too_low:{vol:.0f}"
            if vol > VOLUME_MAX_USD_FALLBACK:
                return f"volume_too_high:{vol:.0f}"

        if t.token_age_days is not None and t.token_age_days > self.age_max_days:
            return f"too_old:{t.token_age_days}d"

        if (
            t.price_change_24h_pct is not None
            and abs(t.price_change_24h_pct) > self.price_change_max
        ):
            return f"already_pumping:{t.price_change_24h_pct:.1f}%"

        return None
