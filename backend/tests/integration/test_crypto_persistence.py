"""DB-backed checks for crypto persistence."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.crypto_trading import AgentVote, MarketSnapshot, NewsEvent, TradeProposal
from app.db.models.project import Project
from app.db.models.user import User
from app.db.models.workflow import Run
from app.db.session import get_worker_db_context
from app.services.crypto_persistence import CryptoPersistenceService


@pytest.fixture
async def db_session() -> AsyncSession:
    async with get_worker_db_context() as session:
        yield session


async def _seed_scope(db: AsyncSession) -> tuple[User, Project, Run]:
    user = User(
        email=f"crypto-persist-{uuid4().hex[:8]}@example.com",
        hashed_password="x",
        role="user",
        is_active=True,
        is_app_admin=False,
    )
    db.add(user)
    await db.flush()

    project = Project(user_id=user.id, name=f"Crypto Persist {uuid4().hex[:6]}")
    db.add(project)
    await db.flush()

    run = Run(project_id=project.id, trigger="manual", input_payload_json={"symbol": "BTCUSDT"})
    db.add(run)
    await db.flush()
    return user, project, run


async def _cleanup_scope(db: AsyncSession, user: User, project: Project, run: Run) -> None:
    await db.execute(delete(TradeProposal).where(TradeProposal.project_id == project.id))
    await db.execute(delete(AgentVote).where(AgentVote.project_id == project.id))
    await db.execute(delete(MarketSnapshot).where(MarketSnapshot.project_id == project.id))
    await db.execute(delete(NewsEvent).where(NewsEvent.project_id == project.id))
    await db.execute(delete(Run).where(Run.id == run.id))
    await db.execute(delete(Project).where(Project.id == project.id))
    await db.execute(delete(User).where(User.id == user.id))
    await db.flush()


@pytest.mark.anyio
async def test_crypto_persistence_saves_run_outputs(db_session: AsyncSession) -> None:
    user, project, run = await _seed_scope(db_session)
    svc = CryptoPersistenceService(db_session)
    try:
        news_payload = {
            "sources_checked": ["yahoo_finance_rss"],
            "news_items": [
                {
                    "news_id": "btc-news-1",
                    "headline": "BTC rallies on ETF optimism",
                    "source": "CoinDesk",
                    "published_at": "2026-06-06T00:00:00Z",
                    "related_assets": ["BTC"],
                    "category": "MACRO",
                    "urgency": "HIGH",
                    "raw_summary": "ETF optimism supports BTC demand.",
                }
            ],
        }
        await svc.persist_agent_output(
            project_id=project.id,
            run_id=run.id,
            agent_role="news_monitor",
            output_text=json.dumps(news_payload),
        )

        reliability_payload = {
            "items": [
                {
                    "news_id": "btc-news-1",
                    "headline": "BTC rallies on ETF optimism",
                    "reliability_score": 88,
                    "reliability_status": "TRUSTED",
                    "risk_flags": [],
                }
            ]
        }
        await svc.persist_agent_output(
            project_id=project.id,
            run_id=run.id,
            agent_role="source_reliability",
            output_text=json.dumps(reliability_payload),
        )

        market_payload = {
            "assessed_at": "2026-06-06T00:05:00Z",
            "market_regime": "RISK_ON",
            "altcoin_condition": "ALTSEASON",
            "btc_condition": "UPTREND",
            "volatility_level": "MEDIUM",
            "fear_greed_index": 62,
            "btc_dominance_pct": 54.2,
            "funding_rate_btc": 0.01,
            "long_short_ratio": 1.1,
            "trade_permission": "ALLOW",
        }
        await svc.persist_agent_output(
            project_id=project.id,
            run_id=run.id,
            agent_role="market_regime",
            output_text=json.dumps(market_payload),
        )

        hawk_payload = {
            "agent": "hawk_trend",
            "vote": "BULLISH",
            "confidence": 82,
            "reasoning": "Trend stack is aligned.",
            "veto_reason": None,
        }
        await svc.persist_agent_output(
            project_id=project.id,
            run_id=run.id,
            agent_role="hawk_trend",
            output_text=json.dumps(hawk_payload),
        )
        await svc.persist_agent_output(
            project_id=project.id,
            run_id=run.id,
            agent_role="hawk_structure",
            output_text=json.dumps({**hawk_payload, "agent": "hawk_structure", "confidence": 79}),
        )
        await svc.persist_agent_output(
            project_id=project.id,
            run_id=run.id,
            agent_role="hawk_counter",
            output_text=json.dumps(
                {**hawk_payload, "agent": "hawk_counter", "vote": "NEUTRAL", "confidence": 61}
            ),
        )
        await svc.persist_agent_output(
            project_id=project.id,
            run_id=run.id,
            agent_role="sage",
            output_text=json.dumps(
                {
                    "agent": "sage",
                    "sage_decision": "APPROVED",
                    "confidence": 77,
                    "reasoning": "Rules passed.",
                    "veto_reason": None,
                }
            ),
        )

        proposal_payload = {
            "symbol": "BTCUSDT",
            "direction": "LONG",
            "strategy_type": "BREAKOUT",
            "time_horizon": "SWING",
            "entry_plan": {
                "primary_entry": 100.0,
                "entry_zone_low": 99.0,
                "entry_zone_high": 101.0,
            },
            "take_profit": [
                {"tp_level": 120.0, "rr_ratio": 2.0, "size_pct": 50},
                {"tp_level": 130.0, "rr_ratio": 3.0, "size_pct": 50},
            ],
            "stop_loss": 90.0,
            "risk_reward": 2.0,
            "position_size_usdt": 50.0,
            "max_loss_usdt": 4.0,
            "total_score": 81.5,
            "sage_approved": True,
            "agent_vote_summary": {"majority_direction": "BULLISH"},
            "news_summary": "ETF optimism remains supportive.",
            "full_proposal_md": "BTC long setup",
        }
        await svc.persist_agent_output(
            project_id=project.id,
            run_id=run.id,
            agent_role="trade_proposal",
            output_text=json.dumps(proposal_payload),
        )

        news_events = (
            (await db_session.execute(select(NewsEvent).where(NewsEvent.project_id == project.id)))
            .scalars()
            .all()
        )
        snapshots = (
            (
                await db_session.execute(
                    select(MarketSnapshot).where(MarketSnapshot.project_id == project.id)
                )
            )
            .scalars()
            .all()
        )
        votes = (
            (await db_session.execute(select(AgentVote).where(AgentVote.project_id == project.id)))
            .scalars()
            .all()
        )
        proposals = (
            (
                await db_session.execute(
                    select(TradeProposal).where(TradeProposal.project_id == project.id)
                )
            )
            .scalars()
            .all()
        )

        assert len(news_events) == 1
        assert news_events[0].reliability_score == 88
        assert news_events[0].used_for_trade is True
        assert len(snapshots) == 1
        assert snapshots[0].market_regime == "RISK_ON"
        assert len(votes) == 4
        assert len(proposals) == 1
        assert proposals[0].status == "PENDING_APPROVAL"
        assert proposals[0].kill_switch_passed is True
        assert proposals[0].hawk_votes == 3
        assert proposals[0].symbol == "BTCUSDT"
        assert proposals[0].expires_at is not None
    finally:
        await _cleanup_scope(db_session, user, project, run)


@pytest.mark.anyio
async def test_crypto_persistence_accepts_fenced_json_output(db_session: AsyncSession) -> None:
    user, project, run = await _seed_scope(db_session)
    svc = CryptoPersistenceService(db_session)
    try:
        fenced = """```json
{"agent":"hawk_trend","vote":"BULLISH","confidence":82,"reasoning":"Trend stack is aligned.","veto_reason":null}
```"""
        await svc.persist_agent_output(
            project_id=project.id,
            run_id=run.id,
            agent_role="hawk_trend",
            output_text=fenced,
        )

        votes = (
            (await db_session.execute(select(AgentVote).where(AgentVote.project_id == project.id)))
            .scalars()
            .all()
        )
        assert len(votes) == 1
        assert votes[0].agent_role == "hawk_trend"
        assert votes[0].vote == "BULLISH"
    finally:
        await _cleanup_scope(db_session, user, project, run)


@pytest.mark.anyio
async def test_crypto_persistence_persists_nested_sage_approved_w13_shape(
    db_session: AsyncSession,
) -> None:
    """W14 regression: sage_approved only under agent_vote_summary must persist a
    PENDING_APPROVAL proposal discoverable by the auto_winrate_gate lookup
    (project_id + run_id + status='PENDING_APPROVAL')."""
    user, project, run = await _seed_scope(db_session)
    svc = CryptoPersistenceService(db_session)
    try:
        proposal_payload = {
            "symbol": "BTCUSDT",
            "direction": "SHORT",
            "strategy_type": "BREAKOUT",
            "time_horizon": "SWING",
            "entry_plan": {
                "primary_entry": 63024.8,
                "entry_zone_low": 62237.2,
                "entry_zone_high": 63024.8,
            },
            "take_profit": [
                {"tp_level": 61274.4, "rr_ratio": 2.0, "size_pct": 50},
                {"tp_level": 60399.2, "rr_ratio": 3.0, "size_pct": 30},
            ],
            "stop_loss": 63900.0,
            "risk_reward": 4.0,
            "position_size_usdt": 50.0,
            "total_score": 60.55,
            "approval_status": "PENDING_APPROVAL",
            # sage_approved NOT at top level — only nested, as in the W13 Auto run.
            "agent_vote_summary": {"majority_direction": "BEARISH", "sage_approved": True},
            "news_summary": "Bearish structure.",
            "full_proposal_md": "BTC short setup",
        }
        await svc.persist_agent_output(
            project_id=project.id,
            run_id=run.id,
            agent_role="trade_proposal",
            output_text=json.dumps(proposal_payload),
        )

        proposal = (
            await db_session.execute(
                select(TradeProposal).where(
                    TradeProposal.project_id == project.id,
                    TradeProposal.run_id == run.id,
                    TradeProposal.status == "PENDING_APPROVAL",
                )
            )
        ).scalar_one()
        assert proposal.direction == "SHORT"
        assert proposal.symbol == "BTCUSDT"
        assert proposal.stop_loss == 63900.0
        assert proposal.sage_approved is True
        assert proposal.kill_switch_passed is True
    finally:
        await _cleanup_scope(db_session, user, project, run)


@pytest.mark.anyio
async def test_crypto_persistence_normalizes_trade_proposal_math(db_session: AsyncSession) -> None:
    user, project, run = await _seed_scope(db_session)
    svc = CryptoPersistenceService(db_session)
    try:
        for role, vote in {
            "hawk_trend": "BULLISH",
            "hawk_structure": "BULLISH",
            "hawk_counter": "NEUTRAL",
        }.items():
            await svc.persist_agent_output(
                project_id=project.id,
                run_id=run.id,
                agent_role=role,
                output_text=json.dumps(
                    {
                        "agent": role,
                        "vote": vote,
                        "confidence": 80,
                        "reasoning": "ok",
                        "veto_reason": None,
                    }
                ),
            )

        proposal_payload = {
            "symbol": "BTCUSDT",
            "direction": "LONG",
            "strategy_type": "BREAKOUT",
            "time_horizon": "SWING",
            "entry_plan": {
                "primary_entry": 63500.0,
                "entry_zone_low": 63200.0,
                "entry_zone_high": 63800.0,
            },
            "take_profit": [
                {"tp_level": 64700.0, "rr_ratio": 2.0, "size_pct": 50},
                {"tp_level": 65900.0, "rr_ratio": 3.0, "size_pct": 30},
            ],
            "stop_loss": 62300.0,
            "risk_reward": 9.9,
            "position_size_usdt": 50.0,
            "max_loss_usdt": 999.0,
            "total_score": 81.5,
            "sage_approved": True,
            "agent_vote_summary": {"majority_direction": "BULLISH"},
            "news_summary": "setup",
            "full_proposal_md": "BTC long setup",
        }
        await svc.persist_agent_output(
            project_id=project.id,
            run_id=run.id,
            agent_role="trade_proposal",
            output_text=json.dumps(proposal_payload),
        )

        proposal = (
            await db_session.execute(
                select(TradeProposal).where(TradeProposal.project_id == project.id)
            )
        ).scalar_one()
        assert proposal.kill_switch_passed is True
        assert proposal.risk_reward == 2.0
        assert proposal.max_loss_usdt == 0.9449
        assert proposal.take_profit[0]["tp_level"] == 65900.0
        assert proposal.kill_switch_details["proposal_normalized"] is True
    finally:
        await _cleanup_scope(db_session, user, project, run)
