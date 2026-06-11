# Runtime Fallback Implementation Export

Date: 2026-06-11

This export is the short handoff version for implementing and then reviewing role-based runtime and fallback behavior in the crypto agent workflow.

## What To Build

Implement a per-role runtime policy for the 12-agent workflow with:

- `claude-cli` on judgment-heavy roles
- `kimi-cli / kimi-k2.6` on synthesis and narrative roles
- `groq-api` on fast operational roles

Critical roles must pause on repeated failure.
Non-critical roles may continue on fallback.
Execution must never place trade actions after primary and fallback failure.

## Role Policy

| Role | Primary | Fallback 1 | Fallback 2 | Policy |
|---|---|---|---|---|
| `news_monitor` | `kimi-cli / kimi-k2.6` | `groq-api / llama-3.3-70b-versatile` | `claude-cli / claude-sonnet-4-6` | continue |
| `source_reliability` | `claude-cli / claude-sonnet-4-6` | `kimi-cli / kimi-k2.6` | `groq-api / llama-3.3-70b-versatile` | pause |
| `market_regime` | `kimi-cli / kimi-k2.6` | `claude-cli / claude-sonnet-4-6` | `groq-api / llama-3.3-70b-versatile` | continue |
| `hawk_trend` | `groq-api / llama-3.3-70b-versatile` | `kimi-cli / kimi-k2.6` | `claude-cli / claude-sonnet-4-6` | continue |
| `hawk_structure` | `claude-cli / claude-sonnet-4-6` | `kimi-cli / kimi-k2.6` | `groq-api / llama-3.3-70b-versatile` | pause |
| `hawk_counter` | `kimi-cli / kimi-k2.6` | `claude-cli / claude-haiku-4-5-20251001` | `groq-api / llama-3.3-70b-versatile` | continue |
| `sage` | `claude-cli / claude-opus-4-8` or `claude-sonnet-4-6` | `kimi-cli / kimi-k2.6` | `groq-api / llama-3.3-70b-versatile` | pause |
| `trade_proposal` | `claude-cli / claude-sonnet-4-6` | `kimi-cli / kimi-k2.6` | `groq-api / llama-3.3-70b-versatile` | pause |
| `execution` | `groq-api / llama-3.1-8b-instant` | `kimi-cli / kimi-k2.6` | `claude-cli / claude-haiku-4-5-20251001` | stop trade action |
| `position_monitor` | `groq-api / llama-3.1-8b-instant` | `kimi-cli / kimi-k2.6` | `claude-cli / claude-haiku-4-5-20251001` | continue |
| `trade_journal` | `kimi-cli / kimi-k2.6` | `groq-api / llama-3.3-70b-versatile` | `claude-cli / claude-sonnet-4-6` | continue |
| `post_trade_review` | `claude-cli / claude-sonnet-4-6` | `kimi-cli / kimi-k2.6` | `groq-api / llama-3.3-70b-versatile` | continue |

## Workflow Order

1. News monitor
2. Source reliability
3. Market regime
4. HAWK trend
5. HAWK structure
6. HAWK counter
7. HAWK vote gate
8. SAGE risk gate
9. Trade proposal
10. Approval gate
11. Execution
12. Position monitor
13. Trade journal
14. Post-trade review

## Required Code Shape

- Add one backend module as the source of truth for runtime policy by role.
- Persist fallback chain and gate policy in agent config.
- Make fallback execution prefer agent-specific policy.
- Ensure supervisor execution uses the same fallback behavior.
- Add a repair/apply CLI command with `--project-id` and `--dry-run`.
- Add tests.

## Prompt To Give Claude Or Kimi

Use the full note:
- `Doc implement/KIMI_CLAUDE_RUNTIME_FALLBACK_IMPLEMENTATION_NOTE.md`

That file contains:
- the exact role mapping
- implementation requirements
- a Claude-specific prompt
- a Kimi-specific prompt
- the review checklist

## Review After Implementation

Check:
- policy lookup
- agent config persistence
- fallback metadata
- supervisor path behavior
- gate pause/continue rules
- repair/apply command
- lint/test results

## Export Status

This file is the export-ready summary.
