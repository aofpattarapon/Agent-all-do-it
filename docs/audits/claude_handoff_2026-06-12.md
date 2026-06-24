# Claude Handoff Note

Date: 2026-06-12
Project: `pixel_dream_agent`
Purpose: concise implementation handoff covering plan, completed work, current state, and remaining todo items.

## Overall plan

1. Phase 0: baseline audit snapshot
2. Phase 1: target runtime design
3. Phase 2: handoff contracts
4. Phase 3: raw payload persistence
5. Phase 4: deterministic execution preflight
6. Phase 5: trace-grade logging
7. Phase 6: schema and gate alignment
8. Phase 7: mode consistency
9. Phase 8: end-to-end verification before enablement

## What is already done

### Phase 0 complete

Baseline snapshot created for:
- agent configs
- workflows and step order
- schedules
- runtime profile
- trading mode values
- recent runs
- recent run steps
- recent trace events
- fallback chains
- execution path evidence
- HAWK schema vs vote gate
- raw payload persistence fields/tables

Files:
- `docs/audits/phase0_baseline_2026-06-12.md`
- `docs/audits/phase0_baseline_2026-06-12.sql`
- `docs/audits/phase0_baseline_2026-06-12.commands.txt`

### Phase 1 complete

Target runtime design decided:
- keep all 12 named roles visible
- keep actual order placement deterministic
- `Execution Agent` should not place orders
- `Post-Trade Review Agent` should become a real downstream step later

Files:
- `docs/audits/phase1_target_runtime_2026-06-12.md`
- `docs/audits/phase1_target_runtime_2026-06-12.commands.txt`

### Phase 2 complete

Implemented fail-closed handoff contracts.

Code changes:
- `backend/app/services/handoff_contracts.py`
- `backend/app/services/run_executor.py`
- `backend/tests/test_handoff_contracts.py`

Behavior:
- workflow boundaries now validate required structured fields
- missing required fields can block a run
- current pause reasons include `handoff_validation_failed` and `handoff_contract_failed`

Verification:
- `pytest backend/tests/test_handoff_contracts.py`
- passed

Files:
- `docs/audits/phase2_handoff_contracts_2026-06-12.md`
- `docs/audits/phase2_handoff_contracts_2026-06-12.commands.txt`

### Phase 3 complete at code level only

Implemented raw payload persistence paths.

Code changes:
- `backend/app/db/models/crypto_trading.py`
- `backend/app/db/models/__init__.py`
- `backend/app/services/crypto_persistence.py`
- `backend/app/services/run_executor.py`
- `backend/app/api/routes/v1/trading.py`
- `backend/app/crypto/services/execution_service.py`

New files:
- `backend/alembic/versions/2026-06-12_add_crypto_raw_payloads.py`
- `backend/tests/test_crypto_raw_payloads.py`

What was added:
- `CryptoRawPayload` table model
- `TradeProposal.raw_payload`
- `TradeJournal.raw_facts`
- raw market data capture before downstream summarization
- raw journal facts capture in workflow/manual/service execution paths
- SL/TP warnings preserved in execution raw response

Verification:
- `pytest backend/tests/test_handoff_contracts.py backend/tests/test_crypto_raw_payloads.py`
- passed

Important:
- migration file exists
- migration has not been applied to the live DB

Files:
- `docs/audits/phase3_raw_payload_persistence_2026-06-12.md`
- `docs/audits/phase3_raw_payload_persistence_2026-06-12.commands.txt`

### Phase 4 complete at code level

Implemented deterministic execution preflight.

Code changes:
- `backend/app/services/execution_preflight.py`
- `backend/app/agents/tools/exchange_tool.py`
- `backend/app/services/run_executor.py`
- `backend/app/api/routes/v1/trading.py`
- `backend/app/crypto/services/execution_service.py`
- `backend/tests/test_execution_preflight.py`

What was added:
- shared execution preflight helper
- deterministic validation before order submission
- status, expiry, symbol, direction, size, stop loss, take profit checks
- duplicate execution and duplicate open-position checks
- latest market regime passed into kill switch
- spot BUY MARKET requires `notional_usdt`
- spot SELL MARKET uses base `quantity`
- exchange-side preflight for `LOT_SIZE`, `MARKET_LOT_SIZE`, and `NOTIONAL` / `MIN_NOTIONAL`

Verification:
- `pytest backend/tests/test_handoff_contracts.py backend/tests/test_crypto_raw_payloads.py backend/tests/test_execution_preflight.py backend/tests/unit/test_execution_service.py`
- passed

Files:
- `docs/audits/phase4_execution_preflight_2026-06-12.md`
- `docs/audits/phase4_execution_preflight_2026-06-12.commands.txt`

## Current live DB state

Latest DB/schema re-check confirms:
- `alembic_version = d2e3f4a5b6c7`
- Phase 3 migration revision file = `e3f4a5b6c7d8`
- live DB does not have:
  - `crypto_raw_payloads`
  - `trade_proposals.raw_payload`
  - `trade_journal.raw_facts`

Project-specific counts for `288bc95a-b4da-46e7-bdfa-b5630233f586`:
- `trade_proposals = 0`
- `trade_executions = 0`
- `trade_journal = 0`
- `market_snapshots = 56`

Recent blocked runtime evidence:
- run `e09ccbf4-5349-4307-b1f5-f1eb7f1f4781`
- `pause_reason = hawk_invalid_market_data`
- `hawk_vote_gate` shows `gate_passed=false`

Files:
- `docs/audits/phase3_db_schema_check_phase4_recheck_2026-06-12.md`
- `docs/audits/phase3_db_schema_check_phase4_recheck_2026-06-12.sql`
- `docs/audits/phase3_db_schema_check_phase4_recheck_2026-06-12.commands.txt`

## Current practical status

- Phase 0: done
- Phase 1: done
- Phase 2: done and active
- Phase 3: code done, DB rollout not done
- Phase 4: code done, depends on Phase 3 DB rollout for full production readiness
- Phase 5: not started
- Phase 6: not started
- Phase 7: not started
- Phase 8: not started

## Known blockers

1. Phase 3 DB migration is not applied.
2. Current live runs still block at HAWK validation.
3. HAWK output schema and vote gate expectations are still misaligned.
4. Mode consistency across DB schedule input, env, and UI is not solved yet.
5. Trace-grade logging is not implemented yet.

## Recommended next order

1. Apply and verify the Phase 3 migration in the target DB.
2. Re-run a Phase 3/4 live-path verification after migration.
3. Implement Phase 5 trace-grade logging.
4. Implement Phase 6 HAWK schema and gate alignment.
5. Implement Phase 7 mode consistency.
6. Implement Phase 8 full end-to-end traced verification.

## Exact todo list

### Immediate

- apply Alembic migration `e3f4a5b6c7d8`
- verify new table/columns exist in live DB
- verify no runtime insert errors on Phase 3 persistence paths

### Phase 5

- add `handoff_trace_id` across runs, steps, payload persistence, proposals, executions, journals
- log runtime/model/fallback actually used
- log input/output byte sizes
- log validator outcomes
- log persistence IDs

### Phase 6

- align HAWK output schema with vote gate expected schema
- ensure HAWK emits all required market-data quality fields
- remove schema mismatch that currently blocks `hawk_vote_gate`

### Phase 7

- define one authoritative trading mode source
- reconcile DB schedule `project_mode`, env values, backend logic, and UI state
- fail closed on mode disagreement

### Phase 8

- run full traced workflow after migration and schema alignment
- verify proposal creation
- verify execution preflight blocking behavior
- verify execution/journal raw persistence
- verify Celery logs, `trace_events`, `run_steps`, and DB rows end to end

## Files Claude should read first

1. `docs/audits/phase3_db_schema_check_phase4_recheck_2026-06-12.md`
2. `docs/audits/phase4_execution_preflight_2026-06-12.md`
3. `docs/audits/phase3_raw_payload_persistence_2026-06-12.md`
4. `docs/audits/phase2_handoff_contracts_2026-06-12.md`
5. `backend/app/services/execution_preflight.py`
6. `backend/app/services/handoff_contracts.py`
7. `backend/app/services/crypto_persistence.py`
8. `backend/app/services/run_executor.py`

## No behavior-change note for this handoff file

This handoff note only documents status. It does not change runtime behavior.
