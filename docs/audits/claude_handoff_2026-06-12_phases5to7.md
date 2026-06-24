# Claude Handoff Note — Phases 5–7

Date: 2026-06-12
Project: `pixel_dream_agent`
Author: Claude (continuing from Codex handoff `claude_handoff_2026-06-12.md`)

---

## What was done this session

### Phase 3 DB migration — APPLIED

- Command: `uv run python -m alembic upgrade head`
- Revision: `d2e3f4a5b6c7` → `e3f4a5b6c7d8`
- New table: `crypto_raw_payloads` (JSONB persistence, indexed on project_id/run_id/payload_kind)
- New columns: `trade_proposals.raw_payload` (JSONB), `trade_journal.raw_facts` (JSONB)
- Verified live via `psql` on `pixel_dream_agent_db` container.

---

### Phase 5 — Trace-grade logging

File changed: `backend/app/services/run_executor.py`

Added:
- `_htrace(run_id)` static method — 8-char hex prefix for log correlation per run
- **Run start log**: `[htrace] run_start exchange_mode=... trading_mode=... is_live=...` (or `mode_conflict:` if env vars disagree)
- **Step start log**: `[htrace] step_start step=... kind=...` before each `_run_step()` call
- **Step done log**: `[htrace] step_done step=... runtime=... model=... out_bytes=... tokens=...` after each `_run_step()` returns
- **Raw payload ID log**: `[htrace] raw_payload_stored id=... kind=market_data step=...` after `store_raw_payload()` succeeds
- **Handoff pass log**: `[htrace] handoff_ok step_a→step_b` when boundary contract passes (was previously silent)
- **Execution ID log**: `[htrace] execution_persisted id=... status=... mode=...` after `TradeExecution` flush
- **Journal ID log**: `[htrace] journal_persisted journal_id=... position_id=... proposal_id=...` after `TradeJournal` flush

No new tables, no schema changes. Pure logging.

---

### Phase 6 — HAWK schema and gate alignment

#### `backend/app/services/run_executor.py`

**`_run_hawk_vote()` — DQ checks demoted from hard-fail to warnings:**
- Replaced `data_quality_failed_steps` / `data_quality_reasons` tracking with `dq_flags: dict[str, list[str]]`
- Removed `analyzed_at` staleness check entirely (LLM fabricates timestamps; no real signal)
- All 4 DQ checks (no_sources, not_real_market_data, no_market_data_snapshot, price_mismatch) are now non-blocking — they populate `dq_flags[step_key]` and emit an `INFO` log but do NOT null out the vote
- `gate_passed` now only blocks on `invalid_steps` (structural failures) or no 2/3 majority
- Result dict: `dq_flags` added; `data_quality_failed_steps` and `data_quality_reasons` kept as empty lists/dicts for backward compat

**NEUTRAL plurality fix:**
- A 3-way tie (e.g. BULLISH/BEARISH/NEUTRAL 1-1-1) → `reported_direction = "NO_MAJORITY"` (no change)
- A genuine NEUTRAL plurality (e.g. NEUTRAL/NEUTRAL/BEARISH 2-1-0) → `reported_direction = "NEUTRAL"` (was previously "NO_MAJORITY")
- Gate still blocks — only the label is corrected

**Main execute loop — removed `hawk_invalid_market_data` branch:**
- Removed `if dq_steps:` block that called `_block(..., pause_reason="hawk_invalid_market_data")`
- This `pause_reason` is now permanently retired
- No-majority path now includes `dq_flags` in gate_message for observability
- `invalid_steps` still routes to `_fail` (hard failures unchanged)

#### `backend/app/commands/seed_crypto_workflow.py`

**HAWK agent base prompts (`_HAWK_TREND_PROMPT`, `_HAWK_STRUCTURE_PROMPT`, `_HAWK_COUNTER_PROMPT`):**
- Removed "DATA YOU MUST ANALYZE (cite sources): https://api.binance.com/..." sections
- Added "DATA SOURCE — use ONLY the pre-fetched market data injected into this prompt via $market_data. Do NOT attempt to fetch URLs yourself."
- Added `"data_quality": "REAL_MARKET_DATA"` and `"market_data_snapshot": {"price": <float>, "analyzed_interval": "4h"}` to all three OUTPUT FORMAT schemas
- `sources_used` now explicitly says `["pre-fetched market data"]`

**`CRYPTO_TRADE_PIPELINE_WORKFLOW` (Proposal to Execution):**
- Added `fetch_market_data` step (kind: `market_data`, intervals: 4h/1h/1d) as **first step**
- Now matches the Auto 30m workflow structure

**`_TRADE_PIPELINE_STEP_PROMPTS` hawk entries:**
- Updated hawk_trend / hawk_structure / hawk_counter prompts to include `$market_data` injection, matching `_AUTO_PIPELINE_STEP_PROMPTS`

#### `backend/tests/integration/test_hawk_vote_gate.py`

- Test 1 (BULLISH/BEARISH/NEUTRAL): added `pause_reason == "hawk_vote_no_majority"` assertion (previously could be `hawk_invalid_market_data`)
- Test 3 (fenced JSON, 2/3 BULLISH): added `"dq_flags" in payload` assertion
- **New test**: `test_hawk_vote_gate_reports_neutral_plurality` — NEUTRAL/NEUTRAL/BEARISH → blocked, `majority_direction == "NEUTRAL"`
- **New test**: `test_hawk_vote_gate_records_dq_flags_without_blocking` — missing DQ fields → gate PASSES on 2/3 majority, `dq_flags` non-empty, `data_quality_failed_steps == []`

**Seed propagated to live DB:**
- `uv run pixel_dream_agent cmd seed-crypto-workflow --project-id 288bc95a-b4da-46e7-bdfa-b5630233f586`
- Result: 12 agents updated, 5 workflows updated, 4 schedules updated
- Live `agent_configs` for `hawk_trend`, `hawk_structure`, `hawk_counter` now have updated prompts with `REAL_MARKET_DATA` and `market_data_snapshot` in output schema
- Live `Crypto Trade Pipeline — Proposal to Execution` now has 12 steps (was 11), first step = `fetch_market_data`

---

### Phase 7 — Mode consistency

New file: `backend/app/services/trading_mode.py`

- `resolve_trading_mode()` → `TradingModeStatus` — reads `EXCHANGE_MODE` + `TRADING_MODE`, validates each against known values, detects and logs conflicts
- `assert_no_mode_conflict()` — raises `ValueError` if the two vars conflict; use at start of any execution path touching real orders
- `effective_project_mode()` → `"paper"` / `"testnet"` / `"live"` — canonical string for run dispatch payloads

**`backend/app/services/run_executor.py`:**
- Imports `resolve_trading_mode`, `effective_project_mode`
- Logs resolved mode (or conflict warning) at every run start via `_htrace`
- Coin screener dispatch `input_payload_json` now uses `effective_project_mode()` instead of hardcoded `"paper"`

**`backend/app/commands/seed_crypto_workflow.py`:**
- Imports `effective_project_mode`
- Both schedule payload `"project_mode"` values now use `effective_project_mode()` instead of hardcoded `"paper"`

**Current live env conflict detected:**
- `EXCHANGE_MODE=demo` (exchange_tool.py — where orders are actually placed)
- `TRADING_MODE=LIVE` (execution_service.py — HTTP API manual execution path)
- These are **conflicting**: `TRADING_MODE=LIVE` expects `EXCHANGE_MODE=live`, but got `demo`
- `resolve_trading_mode()` will log a WARNING at every run start: `mode_conflict: TRADING_MODE=LIVE expects EXCHANGE_MODE in ['live'], got EXCHANGE_MODE='demo'`
- This conflict does NOT block runs (the log is a warning only) — but it signals that the env needs alignment before going to real live trading

**Recommended env fix (operator action required):**
```bash
# Option A: Align to demo/paper
TRADING_MODE=PAPER   # or TESTNET if you want testnet checks in ExecutionService
EXCHANGE_MODE=demo   # leave as-is

# Option B: Align to live
TRADING_MODE=LIVE
EXCHANGE_MODE=live
LIVE_TRADING_ENABLED=true
```

---

## Test results (final)

```
14 passed, 73 warnings
```

| Test file | Result |
|-----------|--------|
| `test_handoff_contracts.py` | 3/3 PASS |
| `test_crypto_raw_payloads.py` | 3/3 PASS |
| `test_execution_preflight.py` | 3/3 PASS |
| `test_hawk_vote_gate.py` | 5/5 PASS (was 0/3) |

---

## Current practical status

| Phase | Status |
|-------|--------|
| Phase 0 | Done |
| Phase 1 | Done |
| Phase 2 | Done and active |
| Phase 3 | Done — code and DB both applied |
| Phase 4 | Done — code done, production ready |
| Phase 5 | **Done** — structured trace logging in run_executor |
| Phase 6 | **Done** — HAWK gate unblocked, prompts updated, seed propagated |
| Phase 7 | **Done** — `trading_mode.py` module; conflict detection active; env alignment needed |
| Phase 8 | Not started — next |

---

## Remaining blockers

1. **Env mode conflict**: `TRADING_MODE=LIVE` + `EXCHANGE_MODE=demo` — logs a warning at every run start. Operator must align before live trading.
2. **Phase 8 E2E verification**: Full traced workflow run to confirm gate passes end-to-end on a live trigger.
3. **Context truncation** (`context_compaction.py:147`, 220-char limit) — not addressed, Codex Blocker #4.
4. **Hardcoded `market_regime="NEUTRAL"`** in kill switch (`run_executor.py:~1789`) — not addressed, Blocker #7.

---

## Files Claude should read next

For Phase 8 (E2E verification):
1. Trigger a manual run on `Crypto Trade Pipeline — Auto 30m` for `BTCUSDT`
2. Confirm: `fetch_market_data` step completes, HAWK steps emit `data_quality=REAL_MARKET_DATA`, gate passes or blocks cleanly with `pause_reason=hawk_vote_no_majority`, no `hawk_invalid_market_data` in any log
3. Confirm: `crypto_raw_payloads` table gets rows, `trace_events` and `run_steps` populated
