from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc
from typing import Optional

from shared.models import TokenCandidate, TokenStatus, Alert, get_session
from agents.dashboard.auth import get_current_user
from agents.dashboard.schemas import TokenCandidateResponse

router = APIRouter(prefix="/tokens", tags=["tokens"])


@router.get("", response_model=list[TokenCandidateResponse])
async def list_tokens(
    status: Optional[str] = Query(None, description="Filtrar por status: active | removed"),
    pattern: Optional[str] = Query(None, description="Filtrar por patrón: long_pump | classic"),
    min_score: float = Query(0.0, ge=0, le=100),
    limit: int = Query(100, ge=1, le=500),
    _: dict = Depends(get_current_user),
):
    """Lista de tokens en watchlist con sus scores y metadatos."""
    async with get_session() as session:
        query = select(TokenCandidate).order_by(
            desc(TokenCandidate.detection_score)
        ).limit(limit)

        if status:
            query = query.where(TokenCandidate.status == status)
        else:
            query = query.where(TokenCandidate.status == TokenStatus.active)

        if pattern:
            query = query.where(TokenCandidate.pattern_type == pattern)

        if min_score > 0:
            query = query.where(TokenCandidate.detection_score >= min_score)

        rows = (await session.execute(query)).scalars().all()

    return [
        TokenCandidateResponse(
            id=r.id,
            symbol=r.symbol,
            exchange=r.exchange,
            status=r.status.value,
            detection_score=r.detection_score,
            pattern_type=r.pattern_type.value,
            holder_concentration_pct=r.holder_concentration_pct,
            inflow_usd=r.inflow_usd,
            volume_24h_usd=r.volume_24h_usd,
            alert_sent=r.alert_sent,
            added_at=r.added_at,
            last_checked=r.last_checked,
            notes=r.notes,
        )
        for r in rows
    ]


@router.get("/{symbol}", response_model=dict)
async def get_token_detail(
    symbol: str,
    _: dict = Depends(get_current_user),
):
    """Detalle de un token: métricas, historial de alertas."""
    symbol = symbol.upper()
    async with get_session() as session:
        token = (
            await session.execute(
                select(TokenCandidate).where(TokenCandidate.symbol == symbol)
            )
        ).scalar_one_or_none()

        if not token:
            raise HTTPException(status_code=404, detail=f"Token {symbol} no encontrado")

        alerts = (
            await session.execute(
                select(Alert)
                .where(Alert.token_symbol == symbol)
                .order_by(desc(Alert.sent_at))
                .limit(10)
            )
        ).scalars().all()

    return {
        "token": TokenCandidateResponse(
            id=token.id,
            symbol=token.symbol,
            exchange=token.exchange,
            status=str(token.status),
            detection_score=token.detection_score,
            pattern_type=str(token.pattern_type),
            holder_concentration_pct=token.holder_concentration_pct,
            inflow_usd=token.inflow_usd,
            alert_sent=token.alert_sent,
            added_at=token.added_at,
            last_checked=token.last_checked,
            notes=token.notes,
        ),
        "alerts": [
            {
                "id": a.id,
                "score": a.score,
                "pattern_type": a.pattern_type,
                "sent_at": a.sent_at.isoformat(),
                "telegram_message_id": a.telegram_message_id,
            }
            for a in alerts
        ],
    }
