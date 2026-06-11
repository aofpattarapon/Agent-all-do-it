"""Trading routes for proposals, executions, positions, journal, and market state."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, HTTPException, Query, status
from sqlalchemy import desc, select, update

import os

from app.agents.tools.exchange_tool import place_order
from app.api.deps import CurrentUser, DBSession, ProjectSvc
from app.crypto.services.execution_service import ExecutionError, ExecutionService
from app.core.rbac import Permission
from app.db.models.crypto_trading import (
    AgentVote,
    MarketSnapshot,
    NewsEvent,
    Position,
    TokenCandidate,
    TradeExecution,
    TradeJournal,
    TradeProposal,
)
from app.services.kill_switch import KillSwitch

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/projects/{project_id}/trading/proposals")
async def list_proposals(
    project_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    db: DBSession,
    status_filter: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.TRADE_VIEW)
    stmt = select(TradeProposal).where(TradeProposal.project_id == project_id)
    if status_filter:
        stmt = stmt.where(TradeProposal.status == status_filter)
    result = await db.execute(stmt.order_by(desc(TradeProposal.created_at)).limit(limit))
    return [_proposal_to_dict(row) for row in result.scalars().all()]


@router.get("/projects/{project_id}/trading/proposals/{proposal_id}")
async def get_proposal(
    project_id: UUID,
    proposal_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    db: DBSession,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.TRADE_VIEW)
    proposal = await _get_proposal_or_404(db, project_id, proposal_id)
    votes_result = await db.execute(select(AgentVote).where(AgentVote.run_id == proposal.run_id))
    votes = [_vote_to_dict(vote) for vote in votes_result.scalars().all()]
    return {**_proposal_to_dict(proposal), "agent_votes_detail": votes}


@router.post("/projects/{project_id}/trading/proposals/{proposal_id}/approve")
async def approve_proposal(
    project_id: UUID,
    proposal_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    db: DBSession,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.TRADE_APPROVE)
    proposal = await _get_proposal_or_404(db, project_id, proposal_id)
    if proposal.status != "PENDING_APPROVAL":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Proposal is {proposal.status}, not PENDING_APPROVAL",
        )
    if proposal.expires_at and proposal.expires_at < datetime.now(UTC):
        await db.execute(
            update(TradeProposal).where(TradeProposal.id == proposal_id).values(status="EXPIRED")
        )
        await db.commit()
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Proposal has expired")

    await db.execute(
        update(TradeProposal)
        .where(TradeProposal.id == proposal_id)
        .values(status="APPROVED", approved_by=user.id, approved_at=datetime.now(UTC))
    )
    await db.commit()
    return {"status": "APPROVED", "proposal_id": str(proposal_id), "approved_by": str(user.id)}


@router.post("/projects/{project_id}/trading/proposals/{proposal_id}/reject")
async def reject_proposal(
    project_id: UUID,
    proposal_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    db: DBSession,
    body: dict[str, Any] = Body(default={}),
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.TRADE_REJECT)
    proposal = await _get_proposal_or_404(db, project_id, proposal_id)
    if proposal.status not in {"PENDING_APPROVAL", "DRAFT"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot reject proposal in status {proposal.status}",
        )
    await db.execute(
        update(TradeProposal)
        .where(TradeProposal.id == proposal_id)
        .values(status="REJECTED", rejection_reason=body.get("reason", "Rejected by user"))
    )
    await db.commit()
    return {"status": "REJECTED", "proposal_id": str(proposal_id)}


@router.post("/projects/{project_id}/trading/proposals/{proposal_id}/execute")
async def execute_proposal(
    project_id: UUID,
    proposal_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    db: DBSession,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.TRADE_APPROVE)

    # Delegate to ExecutionService for testnet — it handles 12 pre-checks + BinanceFuturesAdapter
    if os.getenv("EXCHANGE_MODE", "paper").lower() == "testnet":
        svc = ExecutionService(db)
        try:
            return await svc.execute(proposal_id, project_id, user.id)
        except ExecutionError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    proposal = await _get_proposal_or_404(db, project_id, proposal_id)
    if proposal.status != "APPROVED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Proposal must be APPROVED before execution, got {proposal.status}",
        )

    existing_result = await db.execute(
        select(TradeExecution).where(
            TradeExecution.project_id == project_id,
            TradeExecution.proposal_id == proposal_id,
            TradeExecution.execution_status.in_(["SUCCESS", "PENDING"]),
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Proposal already has an active execution record",
        )

    entry_price = _entry_price_from_plan(proposal.entry_plan)
    if entry_price <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid entry plan price")

    take_profits = _take_profit_levels(proposal.take_profit)
    ks = KillSwitch(db)
    ks_result = await ks.check(
        project_id=project_id,
        symbol=proposal.symbol,
        direction=proposal.direction,
        stop_loss=proposal.stop_loss,
        take_profit_levels=take_profits,
        proposed_size_usdt=float(proposal.position_size_usdt or 0),
        entry_price=entry_price,
        market_regime="NEUTRAL",
    )
    if not ks_result.passed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "Kill Switch blocked execution", "reasons": ks_result.blocked_reasons},
        )

    size_usdt = ks_result.adjusted_position_size_usdt or float(proposal.position_size_usdt or 0)
    if size_usdt <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid position size")
    amount = round(size_usdt / entry_price, 8)
    side = "buy" if proposal.direction.upper() == "LONG" else "sell"

    result = await place_order(
        symbol=proposal.symbol,
        side=side,
        amount=amount,
        order_type="market",
        price=entry_price,
        stop_loss=proposal.stop_loss,
        take_profits=take_profits,
    )

    execution = TradeExecution(
        project_id=project_id,
        proposal_id=proposal.id,
        exchange=str(result.get("exchange", "paper_trade")),
        order_id=result.get("order_id"),
        symbol=proposal.symbol,
        side=proposal.direction.upper(),
        executed_price=_as_float(result.get("executed_price")),
        size=_as_float(result.get("size")) or amount,
        sl_order_id=result.get("sl_order_id"),
        tp_order_ids=result.get("tp_order_ids") or [],
        execution_status=str(result.get("execution_status", "FAILED")),
        error_message=result.get("error"),
        raw_response=result,
    )
    db.add(execution)
    await db.flush()

    if execution.execution_status == "SUCCESS":
        position = Position(
            project_id=project_id,
            execution_id=execution.id,
            symbol=proposal.symbol,
            side=proposal.direction.upper(),
            entry_price=execution.executed_price or entry_price,
            current_price=execution.executed_price or entry_price,
            size=execution.size or amount,
            stop_loss=proposal.stop_loss,
            take_profits=take_profits,
            status="OPEN",
        )
        db.add(position)
        await db.flush()  # position.id assigned before journal FK

        existing_journal = (
            await db.execute(select(TradeJournal).where(TradeJournal.position_id == position.id))
        ).scalar_one_or_none()
        if existing_journal is None:
            journal = TradeJournal(
                project_id=project_id,
                position_id=position.id,
                symbol=proposal.symbol,
                direction=proposal.direction.upper(),
                entry_price=execution.executed_price or entry_price,
                size=execution.size or amount,
                result="OPEN",
                original_thesis=proposal.full_proposal_md or proposal.news_summary,
                agent_votes=proposal.agent_vote_summary or {},
                news_used=[proposal.news_summary] if proposal.news_summary else [],
                decision_log=[
                    {
                        "timestamp": datetime.now(UTC).isoformat(),
                        "action": "executed",
                        "exchange": execution.exchange,
                        "order_id": execution.order_id or "",
                        "entry_price": execution.executed_price or entry_price,
                    }
                ],
            )
            db.add(journal)

    # Let get_db_session auto-commit — no explicit db.commit() here.
    await db.flush()
    await db.refresh(execution)
    return _execution_to_dict(execution)


@router.get("/projects/{project_id}/trading/executions")
async def list_executions(
    project_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    db: DBSession,
    limit: int = Query(50, ge=1, le=200),
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.TRADE_VIEW)
    result = await db.execute(
        select(TradeExecution)
        .where(TradeExecution.project_id == project_id)
        .order_by(desc(TradeExecution.created_at))
        .limit(limit)
    )
    return [_execution_to_dict(item) for item in result.scalars().all()]


@router.get("/projects/{project_id}/trading/positions")
async def list_positions(
    project_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    db: DBSession,
    status_filter: str = Query("OPEN"),
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.TRADE_VIEW)
    result = await db.execute(
        select(Position)
        .where(Position.project_id == project_id, Position.status == status_filter)
        .order_by(desc(Position.created_at))
    )
    return [_position_to_dict(item) for item in result.scalars().all()]


@router.get("/projects/{project_id}/trading/journal")
async def list_journal(
    project_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    db: DBSession,
    limit: int = Query(50, ge=1, le=200),
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.TRADE_VIEW)
    result = await db.execute(
        select(TradeJournal)
        .where(TradeJournal.project_id == project_id)
        .order_by(desc(TradeJournal.created_at))
        .limit(limit)
    )
    return [_journal_to_dict(item) for item in result.scalars().all()]


@router.get("/projects/{project_id}/trading/journal/{journal_id}")
async def get_journal_entry(
    project_id: UUID,
    journal_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    db: DBSession,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.TRADE_VIEW)
    result = await db.execute(
        select(TradeJournal).where(
            TradeJournal.project_id == project_id,
            TradeJournal.id == journal_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Journal entry not found")
    return _journal_to_dict(row)


@router.get("/projects/{project_id}/trading/performance")
async def get_performance(
    project_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    db: DBSession,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.TRADE_VIEW)
    result = await db.execute(
        select(TradeJournal).where(TradeJournal.project_id == project_id).order_by(TradeJournal.created_at)
    )
    trades = result.scalars().all()
    if not trades:
        return {"total_trades": 0, "wins": 0, "losses": 0, "winrate_pct": 0, "total_pnl_usdt": 0}

    wins = [trade for trade in trades if trade.result == "WIN"]
    losses = [trade for trade in trades if trade.result == "LOSS"]
    total_pnl = sum(float(trade.realized_pnl or 0) for trade in trades)
    avg_win = sum(float(trade.realized_pnl or 0) for trade in wins) / len(wins) if wins else 0.0
    avg_loss = sum(float(trade.realized_pnl or 0) for trade in losses) / len(losses) if losses else 0.0
    gross_profit = sum(float(trade.realized_pnl or 0) for trade in wins if (trade.realized_pnl or 0) > 0)
    gross_loss = abs(
        sum(float(trade.realized_pnl or 0) for trade in losses if (trade.realized_pnl or 0) < 0)
    )
    pnl_curve: list[dict[str, Any]] = []
    running = 0.0
    for trade in trades:
        running += float(trade.realized_pnl or 0)
        pnl_curve.append(
            {"date": trade.created_at.isoformat(), "cumulative_pnl": round(running, 2)}
        )

    return {
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "winrate_pct": round((len(wins) / len(trades)) * 100, 1),
        "total_pnl_usdt": round(total_pnl, 2),
        "avg_win_usdt": round(avg_win, 2),
        "avg_loss_usdt": round(avg_loss, 2),
        "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss > 0 else 0,
        "pnl_curve": pnl_curve,
    }


@router.get("/projects/{project_id}/trading/news")
async def list_news(
    project_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    db: DBSession,
    limit: int = Query(30, ge=1, le=200),
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.TRADE_VIEW)
    result = await db.execute(
        select(NewsEvent)
        .where(NewsEvent.project_id == project_id)
        .order_by(desc(NewsEvent.created_at))
        .limit(limit)
    )
    return [
        {
            "id": str(item.id),
            "news_id": item.news_id,
            "headline": item.headline,
            "source": item.source,
            "source_type": item.source_type,
            "category": item.category,
            "urgency": item.urgency,
            "reliability_score": item.reliability_score,
            "reliability_status": item.reliability_status,
            "related_assets": item.related_assets,
            "published_at": item.published_at.isoformat() if item.published_at else None,
            "used_for_trade": item.used_for_trade,
        }
        for item in result.scalars().all()
    ]


@router.get("/projects/{project_id}/trading/candidates")
async def list_candidates(
    project_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    db: DBSession,
    limit: int = Query(30, ge=1, le=200),
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.TRADE_VIEW)
    result = await db.execute(
        select(TokenCandidate)
        .where(TokenCandidate.project_id == project_id)
        .order_by(desc(TokenCandidate.created_at))
        .limit(limit)
    )
    return [
        {
            "id": str(item.id),
            "symbol": item.symbol,
            "trend": item.trend,
            "trend_stage": item.trend_stage,
            "liquidity_score": item.liquidity_score,
            "momentum_score": item.momentum_score,
            "risk_score": item.risk_score,
            "technical_score": item.technical_score,
            "onchain_score": item.onchain_score,
            "sentiment_score": item.sentiment_score,
            "total_score": item.total_score,
            "candidate_status": item.candidate_status,
            "signals": item.signals,
            "created_at": item.created_at.isoformat(),
        }
        for item in result.scalars().all()
    ]


@router.get("/projects/{project_id}/trading/market-snapshot")
async def get_market_snapshot(
    project_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    db: DBSession,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.TRADE_VIEW)
    result = await db.execute(
        select(MarketSnapshot)
        .where(MarketSnapshot.project_id == project_id)
        .order_by(desc(MarketSnapshot.created_at))
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return {"market_regime": "UNKNOWN", "trade_permission": "UNKNOWN"}
    return {
        "market_regime": row.market_regime,
        "btc_condition": row.btc_condition,
        "altcoin_condition": row.altcoin_condition,
        "volatility_level": row.volatility_level,
        "fear_greed_index": row.fear_greed_index,
        "btc_dominance": row.btc_dominance,
        "funding_rate_btc": row.funding_rate_btc,
        "long_short_ratio": row.long_short_ratio,
        "trade_permission": row.trade_permission,
        "snapshot_at": row.snapshot_at.isoformat(),
    }


@router.post("/internal/kill-switch/check")
async def kill_switch_check(
    db: DBSession,
    payload: dict[str, Any] = Body(...),
) -> Any:
    """Internal endpoint for workflow steps that need deterministic risk gates."""
    ks = KillSwitch(db)
    result = await ks.check(
        project_id=UUID(payload["project_id"]),
        symbol=payload.get("symbol", "BTCUSDT"),
        direction=payload.get("direction", "LONG"),
        stop_loss=payload.get("stop_loss"),
        take_profit_levels=payload.get("take_profits", []),
        proposed_size_usdt=float(payload.get("size_usdt", 40)),
        entry_price=float(payload.get("entry_price", 0)),
        market_regime=payload.get("market_regime", "NEUTRAL"),
    )
    return {
        "passed": result.passed,
        "blocked_reasons": result.blocked_reasons,
        "warnings": result.warnings,
        "adjusted_size_usdt": result.adjusted_position_size_usdt,
        "checks_run": result.checks_run,
    }


async def _get_proposal_or_404(db: DBSession, project_id: UUID, proposal_id: UUID) -> TradeProposal:
    result = await db.execute(
        select(TradeProposal).where(
            TradeProposal.project_id == project_id,
            TradeProposal.id == proposal_id,
        )
    )
    proposal = result.scalar_one_or_none()
    if proposal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trade proposal not found")
    return proposal


def _entry_price_from_plan(entry_plan: dict[str, Any]) -> float:
    for key in ("primary_entry", "entry", "price", "avg_entry", "target_entry"):
        value = entry_plan.get(key)
        parsed = _as_float(value)
        if parsed and parsed > 0:
            return parsed
    levels = entry_plan.get("levels")
    if isinstance(levels, list) and levels:
        parsed = _as_float(levels[0])
        if parsed and parsed > 0:
            return parsed
    return 0.0


def _take_profit_levels(raw_levels: Any) -> list[float]:
    values: list[float] = []
    for item in raw_levels or []:
        if isinstance(item, dict):
            candidate = item.get("tp_level") or item.get("price") or item.get("target")
        else:
            candidate = item
        parsed = _as_float(candidate)
        if parsed is not None:
            values.append(parsed)
    return values


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _proposal_to_dict(proposal: TradeProposal) -> dict[str, Any]:
    return {
        "id": str(proposal.id),
        "project_id": str(proposal.project_id),
        "run_id": str(proposal.run_id),
        "symbol": proposal.symbol,
        "direction": proposal.direction,
        "strategy_type": proposal.strategy_type,
        "time_horizon": proposal.time_horizon,
        "entry_plan": proposal.entry_plan,
        "take_profit": proposal.take_profit,
        "stop_loss": proposal.stop_loss,
        "risk_reward": proposal.risk_reward,
        "position_size_usdt": proposal.position_size_usdt,
        "max_loss_usdt": proposal.max_loss_usdt,
        "total_score": proposal.total_score,
        "hawk_votes": proposal.hawk_votes,
        "sage_approved": proposal.sage_approved,
        "kill_switch_passed": proposal.kill_switch_passed,
        "kill_switch_details": proposal.kill_switch_details,
        "agent_vote_summary": proposal.agent_vote_summary,
        "news_summary": proposal.news_summary,
        "status": proposal.status,
        "expires_at": proposal.expires_at.isoformat() if proposal.expires_at else None,
        "approved_by": str(proposal.approved_by) if proposal.approved_by else None,
        "approved_at": proposal.approved_at.isoformat() if proposal.approved_at else None,
        "rejection_reason": proposal.rejection_reason,
        "full_proposal_md": proposal.full_proposal_md,
        "created_at": proposal.created_at.isoformat(),
        "updated_at": proposal.updated_at.isoformat() if proposal.updated_at else None,
    }


def _vote_to_dict(vote: AgentVote) -> dict[str, Any]:
    return {
        "agent_name": vote.agent_name,
        "agent_role": vote.agent_role,
        "vote": vote.vote,
        "confidence": vote.confidence,
        "reasoning": vote.reasoning,
        "veto_reason": vote.veto_reason,
        "created_at": vote.created_at.isoformat(),
    }


def _execution_to_dict(execution: TradeExecution) -> dict[str, Any]:
    return {
        "id": str(execution.id),
        "proposal_id": str(execution.proposal_id),
        "exchange": execution.exchange,
        "order_id": execution.order_id,
        "symbol": execution.symbol,
        "side": execution.side,
        "executed_price": execution.executed_price,
        "size": execution.size,
        "sl_order_id": execution.sl_order_id,
        "tp_order_ids": execution.tp_order_ids,
        "execution_status": execution.execution_status,
        "error_message": execution.error_message,
        "raw_response": execution.raw_response,
        "created_at": execution.created_at.isoformat(),
    }


def _position_to_dict(position: Position) -> dict[str, Any]:
    return {
        "id": str(position.id),
        "symbol": position.symbol,
        "side": position.side,
        "entry_price": position.entry_price,
        "current_price": position.current_price,
        "size": position.size,
        "stop_loss": position.stop_loss,
        "take_profits": position.take_profits,
        "unrealized_pnl": position.unrealized_pnl,
        "unrealized_pnl_pct": position.unrealized_pnl_pct,
        "status": position.status,
        "closed_at": position.closed_at.isoformat() if position.closed_at else None,
        "close_price": position.close_price,
        "realized_pnl": position.realized_pnl,
        "close_reason": position.close_reason,
        "created_at": position.created_at.isoformat(),
    }


def _journal_to_dict(journal: TradeJournal) -> dict[str, Any]:
    return {
        "id": str(journal.id),
        "position_id": str(journal.position_id),
        "symbol": journal.symbol,
        "direction": journal.direction,
        "entry_price": journal.entry_price,
        "exit_price": journal.exit_price,
        "size": journal.size,
        "realized_pnl": journal.realized_pnl,
        "realized_pnl_pct": journal.realized_pnl_pct,
        "holding_time_minutes": journal.holding_time_minutes,
        "result": journal.result,
        "original_thesis": journal.original_thesis,
        "what_happened": journal.what_happened,
        "mistakes": journal.mistakes,
        "what_worked": journal.what_worked,
        "improvement": journal.improvement,
        "post_review_md": journal.post_review_md,
        "decision_log": journal.decision_log,
        "news_used": journal.news_used,
        "agent_votes": journal.agent_votes,
        "created_at": journal.created_at.isoformat(),
    }
