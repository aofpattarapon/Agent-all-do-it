# Phase 3 DB Schema Check + Phase 4 Re-check

Date: 2026-06-12
Project: `pixel_dream_agent`
Scope:
- inspect current DB schema for the Phase 3 table/columns
- confirm whether Phase 3 is active in the database
- re-check Phase 4 on top of that database state

## Files created/updated

Created:
- `docs/audits/phase3_db_schema_check_phase4_recheck_2026-06-12.md`
- `docs/audits/phase3_db_schema_check_phase4_recheck_2026-06-12.sql`
- `docs/audits/phase3_db_schema_check_phase4_recheck_2026-06-12.commands.txt`

Updated:
- none

## SQL commands used

Recorded in:
- `docs/audits/phase3_db_schema_check_phase4_recheck_2026-06-12.sql`

## Terminal commands used

Recorded in:
- `docs/audits/phase3_db_schema_check_phase4_recheck_2026-06-12.commands.txt`

## Exact evidence summary

### 1. Phase 3 schema is not applied in the live database

Evidence:
- `alembic_version.version_num = d2e3f4a5b6c7`
- Phase 3 migration revision file declares `revision = e3f4a5b6c7d8`
- `information_schema.tables` returns no `crypto_raw_payloads`
- `information_schema.columns` returns no `trade_proposals.raw_payload`
- `information_schema.columns` returns no `trade_journal.raw_facts`

Conclusion:
- Phase 3 code exists in the repo, but Phase 3 is not active in the target database.

### 2. Live project state does not yet prove any Phase 3 raw-persistence path

Project-specific counts for `288bc95a-b4da-46e7-bdfa-b5630233f586`:
- `trade_proposals = 0`
- `trade_executions = 0`
- `trade_journal = 0`
- `market_snapshots = 56`

Conclusion:
- raw market snapshots are being persisted through the existing table
- no proposal, execution, or journal rows currently exist for this project
- the new Phase 3 DB fields are therefore not being exercised successfully in production yet

### 3. Recent run evidence remains consistent with the earlier audit

Recent runs:
- `cba4e19c-67d1-42b0-8b76-fd84ef302033` completed
- `e70fd1b4-877c-431d-9068-1fe588dc0984` completed
- `e09ccbf4-5349-4307-b1f5-f1eb7f1f4781` blocked with `pause_reason=hawk_invalid_market_data`

Blocked run step evidence:
- `fetch_market_data` completed and stored market data into `run_steps.output_json`
- `hawk_trend`, `hawk_structure`, `hawk_counter` completed
- `hawk_vote_gate` completed with `gate_passed=false`
- gate reason preview shows: `HAWK vote gate blocked: data quality failed ... not_real_market_data(missing)`

Conclusion:
- current runtime is actively using the stricter Phase 2 gate behavior
- current blockage is still the HAWK data-quality/schema path, not execution preflight

### 4. Worker/backend log evidence does not show a live Phase 3 schema crash in the sampled window

Worker log tail shows:
- Celery `execute_run` tasks received and completed
- OpenRouter prompt execution for `Crypto News Monitor`, `Source Reliability Agent`, `Market Regime Agent`, and `Position Monitor Agent`
- no sampled `UndefinedColumn`, `UndefinedTable`, or raw-payload insert error in the tailed logs

Important interpretation:
- absence of schema errors in this window does not mean Phase 3 is active
- it only means the sampled live runs did not hit a code path that required the missing Phase 3 schema objects

### 5. Phase 4 code re-check passes

Code evidence confirmed:
- deterministic preflight helper exists in `backend/app/services/execution_preflight.py`
- shared order validator exists in `backend/app/agents/tools/exchange_tool.py`
- manual/API execution route calls `prepare_execution_plan(...)` before `place_order(...)`
- spot BUY path passes `notional_usdt` into `place_order(...)`
- testnet execution service still performs deterministic checks and preserves SL/TP warning facts

Verification:
- `python3 -m py_compile ...` passed
- `pytest -q backend/tests/test_handoff_contracts.py backend/tests/test_crypto_raw_payloads.py backend/tests/test_execution_preflight.py backend/tests/unit/test_execution_service.py` passed
- result: `17 passed`

### 6. Phase 4 status on top of the current DB state

Assessment:
- Phase 4 code is present and test-clean
- Phase 4 validation logic is ready at the code level
- Phase 4 is not fully production-ready together with Phase 3 because the live database still lacks:
  - `crypto_raw_payloads`
  - `trade_proposals.raw_payload`
  - `trade_journal.raw_facts`

Practical effect:
- any runtime path that attempts to persist the new Phase 3 payload fields before the DB migration is applied can fail when those paths are reached
- current logs do not prove those paths are safe against the current live schema

## Final status

- Phase 3 code: implemented
- Phase 3 DB rollout: not applied
- Phase 3 active in live DB: no
- Phase 4 code: implemented
- Phase 4 verification: pass
- Safe to continue to later code phases: yes, if DB rollout is intentionally deferred
- Safe to treat Phase 3/4 as fully active in production: no, not until the Phase 3 migration is applied and re-verified

## No behavior changes confirmation

Confirmed:
- no runtime code changed in this checkpoint
- no database schema was modified
- no migration was applied
- no schedules, workflows, models, or env values were changed
- this checkpoint only inspected state and produced audit files
