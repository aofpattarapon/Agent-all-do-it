# Phase 0 Baseline Audit Snapshot

Date: 2026-06-12
Scope: read-only baseline capture for `Binance Testnet — BTCUSDT Pipeline`
Project ID: `288bc95a-b4da-46e7-bdfa-b5630233f586`

This snapshot captures the current runtime state before any implementation work. It does not change runtime behavior, database rows, schedules, workflow definitions, or environment values.

## 1. Current `agent_configs` for the 12 real trading agents

Observed in DB for project `288bc95a-b4da-46e7-bdfa-b5630233f586`:

| Order | Name | Role | Active | Runtime | Model | Memory | Context Window | Gate | Fallback Chain |
|---|---|---|---|---|---|---|---:|---|---|
| 0 | Crypto News Monitor | `news_monitor` | `true` | `openrouter-api` | `openai/gpt-oss-120b:free` | `long_term` | 24 | `continue` | `groq-api/llama-3.3-70b-versatile -> openrouter-api/meta-llama/llama-3.3-70b-instruct:free` |
| 1 | Source Reliability Agent | `source_reliability` | `true` | `openrouter-api` | `openai/gpt-oss-120b:free` | `long_term` | 24 | `continue` | same |
| 2 | Market Regime Agent | `market_regime` | `true` | `openrouter-api` | `openai/gpt-oss-120b:free` | `long_term` | 24 | `continue` | same |
| 3 | HAWK — Trend Analyst | `hawk_trend` | `true` | `openrouter-api` | `openai/gpt-oss-120b:free` | `long_term` | 24 | `continue` | same |
| 4 | HAWK — Structure Analyst | `hawk_structure` | `true` | `openrouter-api` | `openai/gpt-oss-120b:free` | `long_term` | 24 | `continue` | same |
| 5 | HAWK — Counter Analyst | `hawk_counter` | `true` | `openrouter-api` | `openai/gpt-oss-120b:free` | `long_term` | 24 | `continue` | same |
| 6 | SAGE — Risk Head | `sage` | `true` | `openrouter-api` | `openai/gpt-oss-120b:free` | `long_term` | 24 | `continue` | same |
| 7 | Trade Proposal Agent | `trade_proposal` | `true` | `openrouter-api` | `openai/gpt-oss-120b:free` | `long_term` | 24 | `continue` | same |
| 8 | Execution Agent | `execution` | `true` | `openrouter-api` | `openai/gpt-oss-120b:free` | `long_term` | 24 | `continue` | same |
| 9 | Position Monitor Agent | `position_monitor` | `true` | `openrouter-api` | `openai/gpt-oss-120b:free` | `long_term` | 24 | `continue` | same |
| 10 | Trade Journal Agent | `trade_journal` | `true` | `openrouter-api` | `openai/gpt-oss-120b:free` | `long_term` | 24 | `continue` | same |
| 11 | Post-Trade Review Agent | `post_trade_review` | `true` | `openrouter-api` | `openai/gpt-oss-120b:free` | `long_term` | 24 | `continue` | same |

## 2. Current workflow definitions and step order

Current DB workflows and normalized step order:

### Crypto Market Watch — Continuous Research
1. `news_scan` — `prompt` — `Crypto News Monitor`
2. `source_check` — `prompt` — `Source Reliability Agent`
3. `market_regime` — `prompt` — `Market Regime Agent`

### Crypto Position Monitor — Active Positions
1. `position_check` — `prompt` — `Position Monitor Agent`

### Crypto Trade Pipeline — Auto 30m
1. `fetch_market_data` — `market_data`
2. `check_trade_lessons` — `kb_search`
3. `hawk_trend` — `prompt` — `HAWK — Trend Analyst`
4. `hawk_structure` — `prompt` — `HAWK — Structure Analyst`
5. `hawk_counter` — `prompt` — `HAWK — Counter Analyst`
6. `hawk_vote_gate` — `hawk_vote`
7. `sage_review` — `prompt` — `SAGE — Risk Head`
8. `compile_proposal` — `prompt` — `Trade Proposal Agent`
9. `auto_winrate_gate` — `winrate_trade_gate`
10. `execute_trade` — `exchange_execute`
11. `journal_entry` — `prompt` — `Trade Journal Agent`

### Crypto Trade Pipeline — Proposal to Execution
1. `check_trade_lessons` — `kb_search`
2. `hawk_trend` — `prompt` — `HAWK — Trend Analyst`
3. `hawk_structure` — `prompt` — `HAWK — Structure Analyst`
4. `hawk_counter` — `prompt` — `HAWK — Counter Analyst`
5. `hawk_vote_gate` — `hawk_vote`
6. `sage_review` — `prompt` — `SAGE — Risk Head`
7. `compile_proposal` — `prompt` — `Trade Proposal Agent`
8. `winrate_trade_gate` — `winrate_trade_gate`
9. `human_approval_gate` — `approval`
10. `execute_trade` — `exchange_execute`
11. `journal_entry` — `prompt` — `Trade Journal Agent`

Phase 0 finding:
- `Execution Agent` exists in `agent_configs` but workflow step kind is `exchange_execute`, not `prompt`.
- `Post-Trade Review Agent` exists in `agent_configs` but is not present in any workflow step list.
- Research agents are in a separate workflow and are not directly wired into the trade pipelines.

## 3. Current schedules

Observed schedule rows:

| Workflow | Enabled | Cron | Timezone | Input Payload Summary |
|---|---|---|---|---|
| Crypto Market Watch — Continuous Research | `true` | `*/20 * * * *` | `UTC` | `{"symbol":"BTCUSDT","timeframe":"4h","project_mode":"paper"}` |
| Crypto Position Monitor — Active Positions | `true` | `*/5 * * * *` | `UTC` | `{"symbol":"BTCUSDT","timeframe":"4h","project_mode":"paper"}` |
| Crypto Trade Pipeline — Auto 30m | `true` | `*/30 * * * *` | `UTC` | `{"symbol":"BTCUSDT","timeframe":"4h","project_mode":"paper"}` |
| Crypto Trade Pipeline — Proposal to Execution | `true` | `0 * * * *` | `UTC` | `{"symbol":"BTCUSDT","timeframe":"4h","project_mode":"paper"}` |

## 4. Current runtime profile

Observed in `app_settings`:

- Key: `project.288bc95a-b4da-46e7-bdfa-b5630233f586.runtime_profile`
- Value: `test`

## 5. Current trading mode values from DB, schedule, `.env`, UI/config

### DB
- No project secret rows currently exist in `secrets` for this project.
- No DB row was found for exchange mode or live/testnet override beyond the runtime profile setting above.

### Schedule payload
- All four schedules currently inject `project_mode: "paper"`.

### Backend `.env`
Read from `backend/.env`:

- `TRADING_MODE=LIVE`
- `EXCHANGE=BINANCE_FUTURES`
- `BINANCE_ENVIRONMENT=LIVE`
- `EXCHANGE_MODE=demo`
- `MARKET_TYPE=spot`
- `LIVE_TRADING_ENABLED=true`
- `ALLOW_ORDER_EXECUTION=true`
- `REQUIRE_APPROVAL=true`
- `REQUIRE_STOP_LOSS=true`
- `REQUIRE_TAKE_PROFIT=true`
- `BLOCK_IF_SL_ORDER_FAILS=true`
- `BLOCK_DUPLICATE_POSITION=true`
- `KILL_SWITCH_ENABLED=true`
- `HAWK_VOTE_CODE_GATE_REQUIRED=true`
- `SAGE_APPROVAL_REQUIRED=true`

### UI/config if available
- `frontend/src/app/[locale]/(dashboard)/admin/setup/page.tsx` currently writes a project secret named `EXCHANGE_MODE` with value `live` if `liveTrading` is enabled, else `testnet`.
- No such project secret rows exist in the current DB snapshot for this project.

Phase 0 finding:
- Current mode state is inconsistent across sources: schedule payload says `paper`, while backend `.env` says `TRADING_MODE=LIVE`, `EXCHANGE_MODE=demo`, `MARKET_TYPE=spot`, and `LIVE_TRADING_ENABLED=true`.

## 6. Recent workflow runs

Most recent runs observed:

| Run ID | Workflow | Trigger | Status | Current Step | Started | Finished | Evidence |
|---|---|---|---|---:|---|---|---|
| `46f91d21-05b6-4d85-99d1-f44a4b6a5548` | Auto 30m | `schedule` | `blocked` | 5 | 04:00:53 UTC | 04:02:24 UTC | blocked at HAWK vote gate due to missing real market data markers |
| `2b65da98-8440-4c67-8198-7498822f3e87` | Proposal to Execution | `schedule` | `blocked` | 4 | 04:00:53 UTC | 04:02:11 UTC | blocked at HAWK vote gate due to missing real market data markers |
| `03d798d1-9196-4ff3-acb7-a2d7e46d4a18` | Position Monitor | `schedule` | `completed` | 1 | 04:00:51 UTC | 04:01:00 UTC | successful prompt run |
| `bb825d65-76d0-4351-8e9f-0d8b88dd09f7` | Research | `schedule` | `completed` | 3 | 04:00:50 UTC | 04:01:44 UTC | successful 3-step research chain |
| `a5f74782-9165-4bf7-bf01-5036810b6ea6` | Auto 30m | `schedule` | `failed` | 0 | 03:30:20 UTC | 03:59:35 UTC | worker crashed mid-execution; no steps executed |

## 7. Recent `run_steps`

Most relevant recent `run_steps` evidence:

- `fetch_market_data` completed in run `46f91d21-05b6-4d85-99d1-f44a4b6a5548`.
- `hawk_trend`, `hawk_structure`, `hawk_counter` completed in both recent trade-pipeline runs using `openrouter-api / openai/gpt-oss-120b:free`.
- `hawk_vote_gate` completed in both recent trade-pipeline runs but returned `gate_passed=false`.
- No `exchange_execute` `run_steps` exist yet for this project.
- Position monitor prompt steps completed successfully in several recent runs.
- Research steps `news_scan`, `source_check`, and `market_regime` completed successfully in recent research runs.

## 8. Recent `trace_events`

Recent `trace_events` confirm:

- `run.blocked` was emitted for both recent trade-pipeline runs.
- `step.started` and `step.completed` exist for HAWK and gate steps.
- `run.completed` exists for the research workflow.
- Trace evidence exists for completed prompt steps, but there is no trace evidence of a successful `exchange_execute` step in this project snapshot.

## 9. Current `fallback_chain` per agent

For all 12 agent rows in `agent_configs`:

```text
Primary:   openrouter-api / openai/gpt-oss-120b:free
Fallback1: groq-api / llama-3.3-70b-versatile
Fallback2: openrouter-api / meta-llama/llama-3.3-70b-instruct:free
Gate:      continue
```

This matches the current `test` runtime profile source of truth.

## 10. Current exchange execution path evidence

### Code path
- Workflow step kind is `exchange_execute`.
- `RunExecutor._run_exchange_execute()` and `RunExecutor._auto_execute_trade_proposal()` perform order placement through `app.agents.tools.exchange_tool.place_order()`.
- Both paths persist `TradeExecution.raw_response` and then create `Position` and deterministic `TradeJournal` rows on success.
- The runtime does not use the `Execution Agent` prompt for order submission in the current workflow path.

### DB evidence
- `trade_proposals` count for this project: `0`
- `trade_executions` count for this project: `0`
- `positions` with `status='OPEN'`: `0`
- `trade_journal` count for this project: `0`
- `run_steps` with `step_kind='exchange_execute'`: `0`

Phase 0 finding:
- The deterministic order path exists in code, but there is no current project evidence of it having executed successfully.

## 11. Current HAWK output schema vs vote gate expected schema

### HAWK validator currently enforces
From `crypto_handoff_validator.validate_hawk_output()`:

- `vote` must be one of `BULLISH`, `BEARISH`, `NEUTRAL`
- `invalidation_level` must be positive, or is auto-repaired from market price
- `confidence` is only a non-critical warning if missing

### HAWK vote gate currently expects
From `RunExecutor._run_hawk_vote()`:

- `vote`
- non-empty `sources_used`
- `data_quality` in `REAL_MARKET_DATA` or `REAL`
- `analyzed_at` present and no older than 2 hours
- `market_data_snapshot` present
- snapshot price within 5% of `fetch_market_data` reference price

### Seeded prompt contract currently shows
Seed prompts emphasize:

- `vote`
- `confidence`
- `invalidation_level`

They do not consistently guarantee:

- `sources_used`
- `data_quality`
- `analyzed_at`
- `market_data_snapshot`

Phase 0 finding:
- The HAWK prompt/validator contract and the HAWK vote gate contract are not aligned. This mismatch is already visible in live run failures:
  - `HAWK vote gate blocked: data quality failed for hawk_trend=not_real_market_data(missing), hawk_structure=not_real_market_data(missing), hawk_counter=not_real_market_data(missing)`

## 12. Current raw payload persistence tables and fields

### Persisted now
- `news_events`
  - Stores normalized article rows.
  - Stores `raw_summary` text per item.
  - Does not store the full raw upstream scanner payload as one canonical JSON blob.
- `market_snapshots`
  - Stores normalized regime fields.
  - Stores `raw_data JSONB` for market regime payload.
- `agent_votes`
  - Stores normalized vote rows only.
  - No full raw HAWK/SAGE payload JSON field.
- `trade_proposals`
  - Stores normalized proposal fields and `full_proposal_md`.
  - No dedicated raw proposal JSON field.
- `trade_executions`
  - Stores `raw_response JSONB`.
- `trade_journal`
  - Stores deterministic journal facts across columns plus `decision_log`, `news_used`, `agent_votes`.
  - No dedicated raw execution payload or raw journal-facts JSON field.

### Current row counts for this project
- `news_events`: `10`
- `market_snapshots`: `48`
- `agent_votes`: `6`
- `trade_proposals`: `0`
- `trade_executions`: `0`
- `trade_journal`: `0`

## Exact evidence summary

1. The live project is present and active in DB as `Binance Testnet — BTCUSDT Pipeline`.
2. All 12 configured trading agents currently use the same free-first runtime/model/fallback stack from the `test` runtime profile.
3. The workflow engine currently runs 4 workflows, not one unified 12-agent chain.
4. `Execution Agent` and `Post-Trade Review Agent` are configured but not part of active workflow execution.
5. Recent trade-pipeline runs are blocking at the HAWK vote gate because HAWK outputs fail the code-level data-quality contract.
6. There is no current DB evidence of trade proposal persistence, execution, open positions, or journal rows for this project.
7. The deterministic exchange execution path exists in code and persists `TradeExecution.raw_response`, but it has not executed for this project in the captured baseline.
8. Trading mode sources are inconsistent: schedules say `paper`, while backend `.env` says `LIVE/demo/spot` with `LIVE_TRADING_ENABLED=true`.
9. Raw payload persistence is partial: `market_snapshots.raw_data` and `trade_executions.raw_response` exist, but there is no raw proposal JSON field and no full raw HAWK/SAGE payload table.
10. No Phase 0 evidence shows runtime behavior was changed during this audit.

## Files created for this snapshot

- `docs/audits/phase0_baseline_2026-06-12.md`
- `docs/audits/phase0_baseline_2026-06-12.sql`
- `docs/audits/phase0_baseline_2026-06-12.commands.txt`

