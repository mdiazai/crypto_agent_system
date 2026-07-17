"""
Scoring combinado: Narrativa (35 pts) + Onchain (40 pts) + Técnico (25 pts).

alt_rank_change y holder_concentration_change no vienen de ninguna API —
se calculan comparando contra el valor guardado del ciclo anterior en
narrative_candidates (ver research_agent._compute_deltas). Un valor None
en cualquier señal simplemente no suma puntos, no rompe el ciclo.
"""
from dataclasses import dataclass, field
from typing import Optional

from .cryptopanic_client import CryptoPanicNews
from .lunarcrush_client import LunarCrushMetrics
from .nansen_client import NansenSmartMoney
from .technical_client import TechnicalSnapshot


@dataclass
class NarrativeScore:
    symbol: str
    narrative_score: float
    onchain_score: float
    technical_score: float
    combined: float
    narrative_desc: str
    educational_glossary: dict = field(default_factory=dict)


class NarrativeScorer:
    def calculate(
        self,
        lc_data: LunarCrushMetrics,
        cp_data: CryptoPanicNews,
        nansen_data: NansenSmartMoney,
        technical_data: TechnicalSnapshot,
        holder_concentration_pct: Optional[float] = None,
        alt_rank_change: Optional[float] = None,
        holder_concentration_change: Optional[float] = None,
    ) -> NarrativeScore:
        narrative, narrative_notes = self._score_narrative(lc_data, cp_data, alt_rank_change)
        onchain, onchain_notes = self._score_onchain(nansen_data, holder_concentration_change)
        technical, technical_notes = self._score_technical(technical_data)

        combined = narrative + onchain + technical
        notes = narrative_notes + onchain_notes + technical_notes

        return NarrativeScore(
            symbol=lc_data.symbol,
            narrative_score=narrative,
            onchain_score=onchain,
            technical_score=technical,
            combined=combined,
            narrative_desc=" · ".join(notes) if notes else "Sin señales destacadas",
            educational_glossary=self._build_glossary(lc_data, nansen_data, technical_data, holder_concentration_pct),
        )

    @staticmethod
    def _score_narrative(
        lc_data: LunarCrushMetrics, cp_data: CryptoPanicNews, alt_rank_change: Optional[float]
    ) -> tuple[float, list[str]]:
        score = 0.0
        notes: list[str] = []

        if lc_data.galaxy_score is not None:
            if lc_data.galaxy_score > 70:
                score += 15
                notes.append(f"Galaxy Score fuerte: {lc_data.galaxy_score:.0f}")
            elif lc_data.galaxy_score > 50:
                score += 8

        if alt_rank_change is not None:
            if alt_rank_change < -10:
                score += 10
                notes.append(f"AltRank mejorando fuerte (Δ{alt_rank_change:.0f})")
            elif alt_rank_change < 0:
                score += 5
                notes.append(f"AltRank mejorando (Δ{alt_rank_change:.0f})")

        if (
            cp_data.positive_news_count > 3
            and (cp_data.avg_panic_score is None or cp_data.avg_panic_score < 30)
        ):
            score += 10
            notes.append(f"{cp_data.positive_news_count} noticias positivas")

        return score, notes

    @staticmethod
    def _score_onchain(
        nansen_data: NansenSmartMoney, holder_concentration_change: Optional[float]
    ) -> tuple[float, list[str]]:
        score = 0.0
        notes: list[str] = []

        inflow = nansen_data.net_flow_24h_usd
        if inflow is not None:
            if inflow > 1_000_000:
                score += 20
                notes.append(f"Smart money: +${inflow / 1e6:.1f}M")
            elif inflow > 100_000:
                score += 12
                notes.append(f"Smart money: +${inflow / 1e3:.0f}K")

        if holder_concentration_change is not None:
            if holder_concentration_change > 5:
                score += 20
                notes.append(f"Concentración holders subiendo fuerte (Δ{holder_concentration_change:.1f}pp)")
            elif holder_concentration_change > 0:
                score += 10
                notes.append(f"Concentración holders subiendo (Δ{holder_concentration_change:.1f}pp)")

        return score, notes

    @staticmethod
    def _score_technical(technical_data: TechnicalSnapshot) -> tuple[float, list[str]]:
        score = 0.0
        notes: list[str] = []

        if technical_data.rsi_1d is not None:
            if 50 <= technical_data.rsi_1d <= 70:
                score += 15
                notes.append(f"RSI zona alcista sana: {technical_data.rsi_1d:.0f}")
            elif 40 <= technical_data.rsi_1d < 50:
                score += 5

        if technical_data.volume_ratio is not None:
            if technical_data.volume_ratio > 1.5:
                score += 10
                notes.append(f"Volumen {technical_data.volume_ratio:.1f}x el promedio 7d")
            elif technical_data.volume_ratio > 1.2:
                score += 5

        return score, notes

    @staticmethod
    def _build_glossary(
        lc_data: LunarCrushMetrics,
        nansen_data: NansenSmartMoney,
        technical_data: TechnicalSnapshot,
        holder_concentration_pct: Optional[float],
    ) -> dict:
        glossary = {}

        if lc_data.galaxy_score is not None:
            glossary["Galaxy Score"] = (
                f"Métrica de LunarCrush que combina precio, impacto social y sentimiento. "
                f"Valor actual: {lc_data.galaxy_score:.0f}/100. > 70 = momentum social fuerte."
            )
        if lc_data.alt_rank is not None:
            glossary["AltRank"] = (
                f"Ranking relativo de LunarCrush frente a todas las demás cryptos "
                f"(precio + actividad social). Posición actual: #{lc_data.alt_rank}. Menor es mejor."
            )
        if technical_data.rsi_1d is not None:
            glossary["RSI"] = (
                f"Relative Strength Index — velocidad del movimiento de precio (0-100). "
                f"Valor actual: {technical_data.rsi_1d:.0f}. "
                f"50-70 = zona alcista saludable. > 70 = sobrecomprado, riesgo de corrección."
            )
        if nansen_data.net_flow_24h_usd is not None:
            glossary["Smart Money Net Flow"] = (
                f"Flujo neto de wallets institucionales/etiquetadas como 'smart money' (Nansen) "
                f"en las últimas 24h. Positivo = acumulación neta. "
                f"Valor: ${nansen_data.net_flow_24h_usd / 1e6:.2f}M"
            )
        elif nansen_data.chain is None:
            glossary["Smart Money Net Flow"] = (
                "No disponible: este token no tiene contrato en una chain que Nansen cubra "
                "(es un activo nativo de layer-1, ej. XRP, HBAR, BTC). No afecta negativamente "
                "el score, simplemente no suma en este pilar."
            )
        if holder_concentration_pct is not None:
            glossary["Concentración de holders"] = (
                f"% del supply en manos de las 10 wallets más grandes. "
                f"Valor actual: {holder_concentration_pct:.1f}%. "
                f"Subir puede indicar acumulación institucional o riesgo de centralización — "
                f"se evalúa junto al resto de señales, no aisladamente."
            )

        return glossary
