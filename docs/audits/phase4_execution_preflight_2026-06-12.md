Phase 4 completed on 2026-06-12.

Scope implemented:
- add deterministic fail-closed execution preflight before all non-LLM order submission paths
- unify proposal/order validation for workflow `exchange_execute`, workflow auto-exec, and API/manual execution
- strengthen testnet `ExecutionService` symbol filter and kill-switch validation using current stored market regime
- preserve existing spot order semantics:
  - BUY MARKET uses `quoteOrderQty`
  - SELL MARKET uses `quantity`

Files created:
- [backend/app/services/execution_preflight.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/app/services/execution_preflight.py:1)
- [backend/tests/test_execution_preflight.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/tests/test_execution_preflight.py:1)

Files updated:
- [backend/app/agents/tools/exchange_tool.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/app/agents/tools/exchange_tool.py:19)
- [backend/app/services/run_executor.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/app/services/run_executor.py:36)
- [backend/app/api/routes/v1/trading.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/app/api/routes/v1/trading.py:30)
- [backend/app/crypto/services/execution_service.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/app/crypto/services/execution_service.py:19)

SQL commands used:
- none

Terminal commands used:
- `sed -n '1,260p' backend/app/agents/tools/exchange_tool.py`
- `sed -n '1500,1995p' backend/app/services/run_executor.py`
- `sed -n '1,260p' backend/app/api/routes/v1/trading.py`
- `sed -n '1,360p' backend/app/crypto/services/execution_service.py`
- `sed -n '260,760p' backend/app/agents/tools/exchange_tool.py`
- `sed -n '1,260p' backend/app/services/kill_switch.py`
- `rg -n "place_order\\(|ExecutionService|KillSwitch|TRADING_MODE|EXCHANGE_MODE|MARKET_TYPE|LIVE_TRADING_ENABLED" backend/app backend/tests frontend/src`
- `python3 -m py_compile backend/app/services/execution_preflight.py backend/app/agents/tools/exchange_tool.py backend/app/services/run_executor.py backend/app/api/routes/v1/trading.py backend/app/crypto/services/execution_service.py backend/tests/test_execution_preflight.py backend/tests/unit/test_execution_service.py`
- `backend/.venv/bin/pytest -q backend/tests/test_handoff_contracts.py backend/tests/test_crypto_raw_payloads.py backend/tests/test_execution_preflight.py backend/tests/unit/test_execution_service.py`

Exact evidence summary:

1. Shared deterministic proposal preflight
- `prepare_execution_plan()` added at [backend/app/services/execution_preflight.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/app/services/execution_preflight.py:97)
- it now fail-closes on:
  - wrong proposal status
  - expired proposal
  - missing symbol
  - invalid direction
  - missing or non-positive entry price
  - missing stop loss
  - missing take profit levels
  - non-positive `position_size_usdt`
  - duplicate active execution record
  - duplicate open same-side position
  - spot short attempts
  - kill-switch blocks
  - exchange/order preflight errors

2. Stored market regime replaces hardcoded `NEUTRAL`
- latest stored regime lookup added at [backend/app/services/execution_preflight.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/app/services/execution_preflight.py:85)
- this is used by `prepare_execution_plan()` and by `ExecutionService._run_pre_checks()` at [backend/app/crypto/services/execution_service.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/app/crypto/services/execution_service.py:138)

3. Final order-request validation before submission
- `validate_order_request()` added at [backend/app/agents/tools/exchange_tool.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/app/agents/tools/exchange_tool.py:19)
- it validates:
  - symbol presence
  - side correctness
  - positive quantity
  - positive stop-loss / TP values when provided
  - live mode requires `LIVE_TRADING_ENABLED=true`
  - spot BUY MARKET requires positive `notional_usdt`
  - spot SELL MARKET requires positive base quantity
- for demo spot it runs `_preflight_spot_order()` before submission
- for futures/testnet/live/demo futures it runs `_preflight_futures_order()` against exchange info and checks:
  - `LOT_SIZE`
  - `MARKET_LOT_SIZE`
  - `NOTIONAL` / `MIN_NOTIONAL`

4. Workflow execution paths now use shared preflight
- `exchange_execute` now blocks before `place_order()` by calling `prepare_execution_plan()` at [backend/app/services/run_executor.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/app/services/run_executor.py:1610)
- auto execution path now does the same at [backend/app/services/run_executor.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/app/services/run_executor.py:1788)
- both paths now use plan-derived `side`, `amount`, `entry_price`, `take_profits`, and `size_usdt`

5. API/manual execution route now uses shared preflight
- route execution now calls `prepare_execution_plan()` before `place_order()` at [backend/app/api/routes/v1/trading.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/app/api/routes/v1/trading.py:165)
- it now passes `notional_usdt=plan.size_usdt` into `place_order()`, which closes the earlier gap for spot BUY MARKET preflight/input semantics

6. Testnet ExecutionService tightened
- `_run_pre_checks()` now validates:
  - direction
  - symbol presence
  - entry price
  - `position_size_usdt`
  - latest stored market regime in kill-switch call
- `_validate_symbol_filters()` added at [backend/app/crypto/services/execution_service.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/app/crypto/services/execution_service.py:351)
- it checks futures `LOT_SIZE`, `MARKET_LOT_SIZE`, and `NOTIONAL` / `MIN_NOTIONAL`
- `_execute_proposal()` now re-runs the same symbol filter validation immediately before submission at [backend/app/crypto/services/execution_service.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/app/crypto/services/execution_service.py:179)

Verification:
- `py_compile` passed
- `pytest` passed: `17 passed`
- tested files:
  - [backend/tests/test_handoff_contracts.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/tests/test_handoff_contracts.py:1)
  - [backend/tests/test_crypto_raw_payloads.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/tests/test_crypto_raw_payloads.py:1)
  - [backend/tests/test_execution_preflight.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/tests/test_execution_preflight.py:1)
  - [backend/tests/unit/test_execution_service.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/tests/unit/test_execution_service.py:1)

Known limitations after Phase 4:
- migration from Phase 3 is still unapplied by design
- mode consistency across DB schedule input, env, and UI is still not unified; that remains later work
- trace-grade byte logging and `handoff_trace_id` propagation remain later work
- spot demo still performs its own internal preflight too; this is intentional redundancy for fail-closed safety

Behavior change note:
- runtime validation behavior changed
- order-capable paths now fail closed before submission when deterministic preflight fails
- trading strategy / model behavior was not changed
