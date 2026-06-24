# Phase 1 Target Runtime Design

Date: 2026-06-12
Scope: design-only runtime target for `Binance Testnet — BTCUSDT Pipeline`
Project ID: `288bc95a-b4da-46e7-bdfa-b5630233f586`
Inputs: `phase0_baseline_2026-06-12.md`, live workflow seed definitions, current run executor, current validators

This document defines the Phase 1 target runtime shape only. It does not change runtime behavior, database rows, schedules, prompts, workflow definitions, environment values, or execution logic.

## Goal

Define one coherent production target for the trading runtime before implementation starts:

- preserve the 12 named roles as the user-facing operating model
- keep LLM use where judgment and synthesis are valuable
- make order execution deterministic and fail-closed
- eliminate dead-agent assumptions in execution-critical paths
- define the exact trade pipeline order that later implementation must enforce

## Baseline constraints carried from Phase 0

1. Current runtime is not a true 12-agent chain.
2. `Execution Agent` is configured in `agent_configs` but current order placement is deterministic `exchange_execute`.
3. `Post-Trade Review Agent` is configured but not wired into active workflows.
4. Research agents are isolated in a separate workflow from the trade pipeline.
5. Recent trade runs block at the HAWK vote gate due to schema mismatch, not due to market-direction disagreement.
6. Current mode sources are inconsistent across schedule payloads, `.env`, and UI-driven project secrets.

## Phase 1 decision

The target runtime will keep all 12 named roles, but it will not make all 12 roles identical workflow step types.

Decision:

- keep `Execution Agent` as a visible pipeline role for validation and execution reporting only
- keep actual order submission deterministic through `exchange_execute`
- keep `Post-Trade Review Agent` as a real downstream analysis role and wire it into the runtime later
- integrate research outputs into the trade pipeline through stored structured payloads, not loose memory summaries

This is the recommended target because it preserves the user-facing 12-agent operating model while preventing an LLM from becoming the canonical order executor.

## Target runtime topology

### Research chain

1. `Crypto News Monitor`
2. `Source Reliability Agent`
3. `Market Regime Agent`

### Trade decision chain

4. deterministic `market_data`
5. `HAWK — Trend Analyst`
6. `HAWK — Structure Analyst`
7. `HAWK — Counter Analyst`
8. deterministic `hawk_vote_gate`
9. `SAGE — Risk Head`
10. `Trade Proposal Agent`

### Execution chain

11. `Execution Agent` as deterministic validation summary role only
12. deterministic `exchange_execute`

### Post-execution chain

13. `Position Monitor Agent`
14. deterministic raw execution/journal persistence
15. `Trade Journal Agent`
16. `Post-Trade Review Agent`

The user-visible operating model remains the original 12 named agents. The implementation model includes deterministic system steps between them.

## Canonical role boundaries

| Role | Target responsibility | LLM allowed | Canonical fact source |
|---|---|---:|---|
| Crypto News Monitor | Collect and summarize current news items | Yes | stored raw news fetch payload |
| Source Reliability Agent | Score reliability and manipulation risk | Yes | stored raw news payload + source metadata |
| Market Regime Agent | Convert structured market/news context into regime classification | Yes | stored raw market data + stored research payloads |
| HAWK — Trend Analyst | Trend analysis vote | Yes | stored raw market snapshot |
| HAWK — Structure Analyst | Structure analysis vote | Yes | stored raw market snapshot |
| HAWK — Counter Analyst | Counter-trend / alternative-case vote | Yes | stored raw market snapshot |
| SAGE — Risk Head | Hard veto and risk discipline | Yes | structured HAWK outputs + regime + market facts |
| Trade Proposal Agent | Produce structured proposal only | Yes | structured upstream facts |
| Execution Agent | Validate execution readiness and produce execution brief | No, not for order placement | deterministic validator result |
| Position Monitor Agent | Interpret live position state and exceptions | Yes | raw exchange/account state |
| Trade Journal Agent | Narrative trade journal entry | Yes | stored raw execution + proposal + position facts |
| Post-Trade Review Agent | Narrative post-trade performance review | Yes | stored raw journal and execution facts |

## Target workflow families

### Workflow A: Continuous Research

Purpose:
- maintain fresh, structured research artifacts that downstream trade workflows can consume by reference

Target order:
1. `news_scan` -> `Crypto News Monitor`
2. `source_check` -> `Source Reliability Agent`
3. `market_regime` -> `Market Regime Agent`

Target output:
- raw news payload persisted first
- normalized news events
- source reliability annotations
- current regime record with raw market payload attached

### Workflow B: Proposal Generation

Purpose:
- produce a trade proposal from current regime plus fresh market data

Target order:
1. deterministic `fetch_market_data`
2. deterministic `load_latest_research_context`
3. `hawk_trend`
4. `hawk_structure`
5. `hawk_counter`
6. deterministic `hawk_vote_gate`
7. `sage_review`
8. `compile_proposal`
9. deterministic `proposal_validation_gate`

Target output:
- validated structured proposal row
- no execution yet

### Workflow C: Approval To Execution

Purpose:
- move a validated proposal through final checks to actual submission

Target order:
1. deterministic `load_validated_proposal`
2. deterministic `human_approval_gate` or deterministic auto-approval gate, depending on mode
3. deterministic `execution_preflight`
4. `Execution Agent` execution brief using validator output only
5. deterministic `exchange_execute`
6. deterministic `persist_execution_facts`
7. `trade_journal`
8. `post_trade_review`

Target output:
- deterministic execution result
- deterministic journal fact record
- narrative journal/review derived from stored raw facts

### Workflow D: Position Monitoring

Purpose:
- monitor active positions and surface action-worthy state changes

Target order:
1. deterministic `load_position_state`
2. `position_check`
3. optional deterministic escalation or recheck triggers

## Exact target order for the intended 12-role chain

When the product is described as a single chain, the target logical order should be:

1. Crypto News Monitor
2. Source Reliability Agent
3. Market Regime Agent
4. HAWK — Trend Analyst
5. HAWK — Structure Analyst
6. HAWK — Counter Analyst
7. SAGE — Risk Head
8. Trade Proposal Agent
9. Execution Agent
10. Position Monitor Agent
11. Trade Journal Agent
12. Post-Trade Review Agent

Implementation note:
- this logical order does not imply direct step-to-step prompt chaining
- deterministic market loading, gating, approval, validation, and exchange submission remain required system steps between the named roles

## Current-to-target mapping

| Current state | Target state |
|---|---|
| Research workflow isolated from trade pipeline | Trade pipeline loads latest persisted research artifacts deterministically |
| `Execution Agent` configured but unused | `Execution Agent` becomes a non-authoritative validation/execution-brief role after deterministic preflight |
| `exchange_execute` is actual order path | keep this as the only order submission path |
| `Post-Trade Review Agent` configured but unused | wire it after journal creation using stored raw execution and journal facts |
| `Position Monitor Agent` separate workflow only | keep separate monitoring workflow, but allow post-execution monitoring triggers |
| Current trade pipeline starts from fresh market data only | target pipeline starts from fresh market data plus latest structured research context |

## Phase 1 implementation boundaries for later phases

The following must remain deterministic-only in later phases:

- `market_data`
- research context loading
- vote aggregation and 2-of-3 HAWK gating
- proposal schema validation
- approval gating
- execution preflight
- exchange order submission
- execution persistence
- journal fact persistence
- mode resolution

The following remain LLM roles:

- research summarization and scoring
- HAWK analysis
- SAGE risk reasoning
- proposal drafting
- position narrative interpretation
- journal narrative
- post-trade review narrative

## Required target invariants

1. No LLM output can directly submit or modify an exchange order.
2. No fallback model may receive compacted or summarized canonical trading fields.
3. Every downstream LLM must read structured persisted upstream facts, not only clipped memory.
4. Every execution-capable workflow must fail closed if required structured fields are missing.
5. Every post-execution narrative must be derived from stored raw execution facts.
6. `Execution Agent` cannot override deterministic preflight or validator failures.
7. `Post-Trade Review Agent` cannot become a source of canonical execution facts.

## Explicit non-goals for Phase 1

Phase 1 does not:

- rewrite workflow definitions
- add or remove DB columns
- change runtime profile or fallback chains
- modify Celery execution behavior
- change prompts
- change approval policies
- enable execution

## Deliverables completed in Phase 1

1. Chosen target runtime shape: keep the 12 named roles, but keep execution deterministic.
2. Chosen target workflow family split: research, proposal, approval-to-execution, monitoring.
3. Chosen target role boundaries: LLM roles vs deterministic-only system steps.
4. Chosen target logical chain ordering for the 12 named roles.
5. Chosen current-to-target migration direction for later implementation phases.

## Phase 1 exit criteria

Phase 1 is complete when the implementation team can answer all of the following without ambiguity:

1. Is `Execution Agent` allowed to place orders directly?
   - No.
2. Is `exchange_execute` still the real order path?
   - Yes.
3. Will `Post-Trade Review Agent` become part of the runtime later?
   - Yes.
4. Will research remain detached from trading decisions?
   - No.
5. Are all 12 named roles preserved in the operating model?
   - Yes.

## No behavior changes confirmation

This Phase 1 work is design-only. No runtime behavior, database state, schedule state, environment value, workflow definition, or agent configuration was changed.
