"""Backtest API — run historical simulations for a project."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, DBSession

router = APIRouter(prefix="/projects/{project_id}/backtest", tags=["backtest"])


class BacktestRequest(BaseModel):
    symbol: str = Field(default="BTCUSDT")
    timeframe: str = Field(default="4h")
    start_date: datetime
    end_date: datetime
    strategy_config: dict[str, Any] = Field(default_factory=dict)


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def run_backtest(
    project_id: UUID,
    body: BacktestRequest,
    db: DBSession,
    user: CurrentUser,
) -> Any:
    from app.services.backtest_engine import BacktestEngine
    try:
        engine = BacktestEngine(db)
        result = await engine.run(
            project_id=project_id,
            symbol=body.symbol,
            timeframe=body.timeframe,
            start_date=body.start_date,
            end_date=body.end_date,
            strategy_config=body.strategy_config,
        )
        return result
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.get("")
async def list_backtests(
    project_id: UUID,
    db: DBSession,
    user: CurrentUser,
) -> Any:
    from sqlalchemy import select
    from app.services.backtest_engine import BacktestResult
    result = await db.execute(
        select(BacktestResult)
        .where(BacktestResult.project_id == project_id)
        .order_by(BacktestResult.created_at.desc())
        .limit(20)
    )
    rows = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "symbol": r.symbol,
            "timeframe": r.timeframe,
            "start_date": r.start_date.isoformat() if r.start_date else None,
            "end_date": r.end_date.isoformat() if r.end_date else None,
            "metrics": r.metrics,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]
