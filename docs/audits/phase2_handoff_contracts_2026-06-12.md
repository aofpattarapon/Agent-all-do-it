# Phase 2 Implementation Audit

Date: 2026-06-12
Scope: explicit handoff contracts and fail-closed validation
Project: `Binance Testnet — BTCUSDT Pipeline`

This phase implemented the handoff-contract layer. It did change runtime behavior for workflow boundary validation, but it did not modify trading mode values, schedules, runtime profiles, fallback chains, exchange execution logic, or raw-payload persistence.

## Objective completed

Implemented:

1. explicit JSON-path handoff contracts for the crypto workflow boundaries
2. downstream-aware contract matching by concrete step key
3. fail-closed blocking when a required boundary field is missing
4. fail-closed blocking when the existing crypto step validator reports critical violations
5. persistence of auto-repaired prompt payloads back into the stored run-step output

Not implemented in this phase:

- raw payload storage changes
- execution preflight hardening
- mode consistency fixes
- trace-grade byte-size logging
- schema alignment between HAWK prompts and the vote gate

## Files changed

Created:

- `backend/tests/test_handoff_contracts.py`

Updated:

- `backend/app/services/handoff_contracts.py`
- `backend/app/services/run_executor.py`

Audit files created:

- `docs/audits/phase2_handoff_contracts_2026-06-12.md`
- `docs/audits/phase2_handoff_contracts_2026-06-12.commands.txt`

## What changed

### 1. `handoff_contracts.py` replaced generic keyword gates

Previous state:

- generic `DEFAULT_CONTRACTS`
- substring concept matching only
- no real JSON validation
- no downstream-step awareness

Current state:

- structured `HandoffField`
- structured `HandoffContract`
- structured `HandoffCheckResult`
- `validate_handoff()` validates concrete JSON field paths
- `contracts_for_handoff()` selects contracts by actual upstream and downstream step keys

Implemented concrete contracts for:

- `news_scan -> source_check`
- `source_check -> market_regime`
- `fetch_market_data -> hawk_trend/hawk_structure/hawk_counter`
- `hawk_trend/hawk_structure/hawk_counter -> hawk_vote_gate`
- `hawk_vote_gate -> sage_review`
- `sage_review -> compile_proposal`
- `compile_proposal -> auto_winrate_gate/winrate_trade_gate/human_approval_gate/execute_trade`
- `execute_trade -> journal_entry`

### 2. `run_executor.py` now blocks on invalid boundaries

Current enforcement points:

- after a step finishes, `RunExecutor._evaluate_boundary_handoff()` checks whether the next workflow step is allowed to consume that payload
- if the contract fails, the run is blocked with:
  - `pause_reason = handoff_contract_failed`
- if the existing crypto validator reports critical field violations, the run is blocked with:
  - `pause_reason = handoff_validation_failed`

### 3. repaired payloads are now written back to the stored step output

When the crypto handoff validator auto-repairs a non-critical field, the modified JSON is now written back to `db_step.output_json` instead of only updating in-memory context.

## Runtime impact

This phase intentionally makes the pipeline stricter.

Expected immediate effect on the current baseline:

- trade runs that previously reached `hawk_vote_gate` and failed there will now fail earlier if a HAWK output omits required fields such as:
  - `data_quality`
  - `market_data_snapshot`
  - `sources_used`
  - `analyzed_at`

That is expected and correct for this phase. The pipeline is now fail-closed at the boundary instead of allowing incomplete payloads to continue downstream.

## Evidence references

Key implementation points:

- `backend/app/services/handoff_contracts.py:67`
- `backend/app/services/handoff_contracts.py:206`
- `backend/app/services/run_executor.py:531`
- `backend/app/services/run_executor.py:544`
- `backend/app/services/run_executor.py:572`
- `backend/app/services/run_executor.py:593`
- `backend/app/services/run_executor.py:1735`
- `backend/tests/test_handoff_contracts.py:10`
- `backend/tests/test_handoff_contracts.py:31`
- `backend/tests/test_handoff_contracts.py:55`

## Verification run

Completed successfully:

1. `python3 -m py_compile` on the modified runtime and test files
2. targeted test run:
   - `backend/tests/test_handoff_contracts.py`

Result:

- `3 passed`

Constraint encountered:

- a DB-backed integration test was attempted first, but local test DB access was blocked by the environment sandbox (`PermissionError` to `127.0.0.1:5433`), so Phase 2 verification was reduced to pure executor-level and service-level tests that do not require a live DB connection.

## Known blocker after Phase 2

Phase 2 exposes an already-known upstream schema problem:

- HAWK prompt outputs are still not aligned with the fields the downstream gate path expects

That means:

- the new contracts are correct
- the current HAWK prompt/schema is still incomplete
- Phase 7 must align prompt output schema with the vote gate and the new contracts

## No out-of-scope changes confirmation

Phase 2 did not change:

- `agent_configs`
- runtime profile selection
- fallback chains
- schedules
- `.env`
- execution sizing semantics
- preflight checks
- raw payload persistence schema
- journal persistence schema
