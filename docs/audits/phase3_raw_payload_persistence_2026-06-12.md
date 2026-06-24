Phase 3 completed on 2026-06-12.

Scope implemented:
- store raw structured payloads before later summarization/normalization where the current code path allows it
- add canonical raw payload fields for trade proposals and trade journals
- preserve execution warnings and IDs in journal raw facts across all three execution paths

Files created:
- [backend/alembic/versions/2026-06-12_add_crypto_raw_payloads.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/alembic/versions/2026-06-12_add_crypto_raw_payloads.py:1)
- [backend/tests/test_crypto_raw_payloads.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/tests/test_crypto_raw_payloads.py:1)
- [docs/audits/phase3_raw_payload_persistence_2026-06-12.md](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/docs/audits/phase3_raw_payload_persistence_2026-06-12.md:1)
- [docs/audits/phase3_raw_payload_persistence_2026-06-12.commands.txt](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/docs/audits/phase3_raw_payload_persistence_2026-06-12.commands.txt:1)

Files updated:
- [backend/app/db/models/crypto_trading.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/app/db/models/crypto_trading.py:38)
- [backend/app/db/models/__init__.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/app/db/models/__init__.py:28)
- [backend/app/services/crypto_persistence.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/app/services/crypto_persistence.py:27)
- [backend/app/services/run_executor.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/app/services/run_executor.py:486)
- [backend/app/api/routes/v1/trading.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/app/api/routes/v1/trading.py:250)
- [backend/app/crypto/services/execution_service.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/app/crypto/services/execution_service.py:175)

SQL commands used:
- none in this phase

Terminal commands used:
- `rg -n "news_events|market_snapshots|trade_proposals|trade_executions|trade_journal|raw_response|raw_data|raw_payload|proposal" ...`
- `sed -n '1,260p' backend/app/services/crypto_persistence.py`
- `sed -n '1,260p' backend/app/db/models/crypto_trading.py`
- `sed -n '1600,1705p' backend/app/services/run_executor.py`
- `sed -n '1800,1905p' backend/app/services/run_executor.py`
- `sed -n '180,270p' backend/app/api/routes/v1/trading.py`
- `sed -n '220,330p' backend/app/crypto/services/execution_service.py`
- `python3 -m py_compile backend/app/db/models/crypto_trading.py backend/app/services/crypto_persistence.py backend/app/services/run_executor.py backend/app/api/routes/v1/trading.py backend/app/crypto/services/execution_service.py backend/tests/test_crypto_raw_payloads.py`
- `backend/.venv/bin/pytest -q backend/tests/test_handoff_contracts.py backend/tests/test_crypto_raw_payloads.py`
- `nl -ba ...` and `rg -n ...` for evidence line numbers

Exact evidence summary:

1. New raw payload storage table
- `CryptoRawPayload` model added at [backend/app/db/models/crypto_trading.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/app/db/models/crypto_trading.py:38)
- migration created at [backend/alembic/versions/2026-06-12_add_crypto_raw_payloads.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/alembic/versions/2026-06-12_add_crypto_raw_payloads.py:21)
- migration adds `crypto_raw_payloads` plus indexes on `project_id`, `run_id`, and `payload_kind`

2. Raw proposal and journal fields added
- `TradeProposal.raw_payload` added at [backend/app/db/models/crypto_trading.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/app/db/models/crypto_trading.py:145)
- `TradeJournal.raw_facts` added at [backend/app/db/models/crypto_trading.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/app/db/models/crypto_trading.py:225)
- migration adds both fields at [backend/alembic/versions/2026-06-12_add_crypto_raw_payloads.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/alembic/versions/2026-06-12_add_crypto_raw_payloads.py:43)

3. Prompt output raw payload capture
- `persist_agent_output()` now writes a raw payload row before branching into news/reliability/regime/vote/proposal persistence at [backend/app/services/crypto_persistence.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/app/services/crypto_persistence.py:66)
- helper `store_raw_payload()` is implemented at [backend/app/services/crypto_persistence.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/app/services/crypto_persistence.py:102)
- this means raw JSON is now retained for `news_monitor`, `source_reliability`, `market_regime`, HAWK roles, `sage`, and `trade_proposal`

4. Raw market data capture before LLM use
- deterministic `market_data` output is now persisted immediately from the workflow executor at [backend/app/services/run_executor.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/app/services/run_executor.py:486)
- payload kind used is `market_data`
- this happens before HAWK/SAGE consume the market payload downstream

5. Raw proposal payload retained on canonical proposal row
- `save_trade_proposal()` now writes the original proposal JSON into `TradeProposal.raw_payload` at [backend/app/services/crypto_persistence.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/app/services/crypto_persistence.py:78) and [backend/app/services/crypto_persistence.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/app/services/crypto_persistence.py:99)
- field assignment happens in the persisted `values` dict at [backend/app/services/crypto_persistence.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/app/services/crypto_persistence.py:381)

6. Raw journal facts retained in all execution paths
- helper `build_trade_journal_raw_facts()` added at [backend/app/services/crypto_persistence.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/app/services/crypto_persistence.py:27)
- workflow `exchange_execute` journal now stores `raw_facts` at [backend/app/services/run_executor.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/app/services/run_executor.py:1694)
- workflow auto-exec journal now stores `raw_facts` at [backend/app/services/run_executor.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/app/services/run_executor.py:1904)
- API/manual execution journal now stores `raw_facts` at [backend/app/api/routes/v1/trading.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/app/api/routes/v1/trading.py:250)
- `ExecutionService` journal now stores `raw_facts` at [backend/app/crypto/services/execution_service.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/app/crypto/services/execution_service.py:301)

7. Execution raw response fidelity improved in direct service path
- `ExecutionService` now accumulates SL/TP warning details into `execution_payload` and writes them back into `TradeExecution.raw_response` at [backend/app/crypto/services/execution_service.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/app/crypto/services/execution_service.py:233) and [backend/app/crypto/services/execution_service.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/app/crypto/services/execution_service.py:275)
- this closes the prior gap where direct execution only stored the entry order response

Verification:
- `py_compile` passed
- `pytest` passed: `6 passed`
- tested files:
  - [backend/tests/test_handoff_contracts.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/tests/test_handoff_contracts.py:1)
  - [backend/tests/test_crypto_raw_payloads.py](/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/tests/test_crypto_raw_payloads.py:1)

Known limitations after Phase 3:
- the migration file was created but not applied in this phase
- there is still no byte-size logging or `handoff_trace_id` propagation in payload records; that remains Phase 5 work
- `news_monitor` raw storage captures the agent JSON batch, not the original external source HTTP payloads, because that fetch layer is not currently exposed as a separate persistence boundary
- structured compaction protection and fail-closed field contracts were not expanded here beyond Phase 2; those remain later phases

Behavior change note:
- runtime behavior for trading decisions was not changed
- persistence behavior did change:
  - more raw JSON is now written when these code paths run
  - proposal rows now retain raw proposal JSON
  - journal rows now retain structured raw facts
  - direct execution service now retains SL/TP warning details in `raw_response`
