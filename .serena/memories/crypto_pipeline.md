# Crypto Trading Pipeline Architecture

## NEXMIND Pipeline (Auto 30m)
Steps: `fetch_market_data → check_trade_lessons → hawk_trend → hawk_structure → hawk_counter → hawk_vote_gate → sage_review → compile_proposal → auto_winrate_gate → execute_trade → journal_entry`

## Key gate behaviors (run_executor.py)
- **hawk_vote_gate**: requires 2/3 HAWK majority → sets `run.status='blocked'`, `run.pause_reason='hawk_vote_no_majority'`
- **SAGE veto**: `sage_decision=VETOED` in any prompt step → `run.status='blocked'`, `run.pause_reason='sage_veto'`
- **winrate_trade_gate**: `step_kind='winrate_trade_gate'`
  - open position cap: `output_json.meta.skip_reason='open_position'` → run continues to journal (completed)
  - below threshold + skip: `output_json.meta.auto_executed=False` → run continues to journal (completed)
  - auto-execute: `output_json.meta.auto_executed=True` → calls `_auto_execute_trade_proposal`

## DB models (crypto_trading.py)
- `TradeProposal`: `run_id` FK, `status` (DRAFT/PENDING_APPROVAL/APPROVED/REJECTED/EXPIRED), `sage_approved`
- `TradeExecution`: `proposal_id` FK, `execution_status` (PENDING/SUCCESS/FAILED/EXECUTED)
- `Position`: `execution_id` FK, `status` (OPEN/CLOSED/PARTIAL)
- `TradeJournal`: `position_id` FK (NOT run_id — journal persists via position link)

## Trade outcome service
`app/services/run_trade_outcome.py` — pure function `build_run_trade_outcome(TradeEvidence) -> dict`
Status precedence: error → active → complete_trade → limit → complete_reject → unknown
Exposed via `trade_outcome` field on `RunRead` schema (additive, never replaces `runs.status`).

## Known issues / fixes applied
- `$run_id` was NOT substituted in `_substitute()` — fixed by adding `run_id` to context dict
  and `result.replace("$run_id", str(context.get("run_id") or ""))` in `run_executor.py`
- Root cause of `run_id: null` in journal output: the `$run_id` placeholder was passed
  literally to the LLM which output null since it couldn't resolve it.
