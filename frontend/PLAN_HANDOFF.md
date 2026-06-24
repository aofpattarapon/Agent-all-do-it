# Pixel Dream Agent — Frontend Plan & Handoff (start → end)

> **Purpose:** Single source of truth for the focused-views work so a fresh model
> (Kimi 2.7) can continue with zero missing context. Covers the full multi-phase
> plan, what is DONE, what is NEXT, the non-negotiable rules, file map, and how to
> verify. Last updated: 2026-06-17.

---

## 0. TL;DR status

| Phase | Scope | Status |
|-------|-------|--------|
| 0 | Baseline / run-status taxonomy foundation | ✅ DONE |
| A | Canonical run taxonomy (`run-status.ts`) + tests | ✅ DONE |
| B | (taxonomy wiring / shared types) | ✅ DONE |
| C | Menu shell + Overview + Readiness badge + tabs | ✅ DONE |
| **D** | **Focused views: Trades / Rejected / Limits / Errors / Performance** | ✅ **DONE (this handoff)** |
| E | Settings readiness panel (in depth) | ⛔ NOT STARTED (placeholder shell only) |
| F | Learning dashboard | ⛔ NOT STARTED (placeholder shell only) |
| — | Agents Quality | ⛔ NOT STARTED (no placeholder needed yet) |

**Next model task:** Phase E (Settings readiness panel) and/or Phase F (Learning
dashboard). Do NOT start them without explicit approval.

---

## 1. Canonical rules (NEVER violate — these govern all phases)

These are the run-outcome taxonomy rules. They are the backbone of the whole UI:

- `display_status` is the **canonical run outcome taxonomy**.
- `isErrorRun` is the **canonical error predicate**.
- `workflowCategoryOf` is **only** for trade / monitor / screener split.
- `statusGroupOf` must **not** drive counts.
- raw `run.status` is **debug/detail/action gating only** — never outcome classification.
- complete-reject is **not** an error and **not** a trade loss.
- HAWK no-majority is **not** a failure.
- `handoff_validation_failed` and `handoff_contract_failed` **are** errors.
- limit is **separate** from error.
- **Trade Win Rate must come from backend performance summary / TradeJournal, not runs.**

### Outcome → view mapping (the filtering contract)

| View | Inclusion predicate | Excludes |
|------|---------------------|----------|
| Trades | built from trading endpoints (executions/positions/journal); run count = `displayStatusOf(run) === "complete-trade"` | reject / limit / error |
| Rejected | `displayStatusOf(run) === "complete-reject"` | error / limit |
| Limits & Safety | `run.is_limit === true \|\| displayStatusOf(run) === "limit"` | error / reject |
| Errors | `isErrorRun(run)` (i.e. `display_status === "error"`) | HAWK no-majority, SAGE veto, complete-reject, limit |
| Performance | metrics from perf summary (+ runs/summary fallback) | Win Rate never derived from runs |

---

## 2. Hard constraints (security / scope — still in force for E/F)

VERBATIM from the approved spec — these continue to bind the next model:

- Do **not** implement Settings readiness panel in depth yet *(that was Phase E — now the NEXT task, only on approval)*.
- Do **not** implement Learning dashboard yet *(Phase F — only on approval)*.
- Do **not** implement Agents Quality yet unless a tiny placeholder connection is required.
- Do **not** modify backend trading logic.
- Do **not** modify validators.
- Do **not** modify HAWK/SAGE prompts.
- Do **not** run migrations.
- Do **not** modify DB data.
- Do **not** place demo/testnet/live orders.
- Do **not** expose secret values (readiness shows only presence booleans / env-var name patterns).

---

## 3. Tech stack & conventions

- Next.js 15 App Router, TypeScript strict with `noUncheckedIndexedAccess` (index access yields `T | undefined` — use `arr[i]!` in tests when provably present).
- Tailwind; pixel-UI design system (`PixelFrame`, `SectionLabel`, `StatCard` from `@/components/pixel-ui`); VT323 monospace font; CSS vars `--pix-danger`, `--pix-success`, `--pix-muted`, `--pix-gold`, `--pix-ink`.
- Data: `@tanstack/react-query`; `apiClient.get<T>(endpoint, opts?)` → hits `/api{endpoint}`. Use `retry: false` for trading endpoints so failures degrade to empty/not-ready states (never fabricate data).
- i18n locale segment in routes (`/[locale]/...`).
- Tests: vitest 2.x + @testing-library/react + jest-dom. Setup `vitest.setup.ts` has `afterEach(cleanup)` and a global `vi.mock("next/navigation", ...)` returning `usePathname: () => "/"`. View tests override that mock per-file.

> **Tooling note:** Project mandates **Serena** semantic tools (`get_symbols_overview`,
> `find_symbol`, `replace_symbol_body`, etc.) for code files; built-in Read/Edit are
> secondary. Markdown/JSON/config may use plain Read/Edit/Write.

### ⚠️ Known test gotcha (carry forward)
When a component issues `apiClient.get()` queries, testing-library's `cleanup()`
afterEach can trigger a stray `apiClient.get()` call with **no args** during
`callCleanupHooks`, crashing on `undefined.endsWith`. **Guard every mock dispatch:**
```ts
getMock.mockImplementation((endpoint?: string) => {
  if (typeof endpoint !== "string") return Promise.resolve(null);
  // ...route by endpoint
});
```

---

## 4. Canonical types & helpers (already built)

- `src/lib/run-status.ts` — `displayStatusOf`, `isErrorRun`, `workflowHealthOf`, `workflowCategoryOf`; `RunStatusInput` (`status`, `workflow_name?`, `pause_reason?`, `trade_outcome?`, plus `RunDisplayFields`: `display_status?`, `is_error?`, `is_limit?`).
- `src/lib/focused-runs.ts` (Phase D) — `FocusedRun` (extends `RunStatusInput` + `id`, `trigger?`, `started_at?`, `finished_at?`, `error_text?`, `output_text?`); `reasonText`, `runSymbol`, `rejectReasonLabel`, `limitReasonLabel`, `limitLooksHealthy`, `runDetailHref(pathname, runId)`.
- `src/types/trading.ts` — `TradeExecution`, `Position` (incl. `execution_visibility`, `realized_pnl`, `unrealized_pnl`, `status`), `TradeJournal`, `TradingReadiness`, `RunSummary` (`by_display_status`, `by_workflow_category`, `trade_pipeline`, `terminal`...), `PerformanceSummary` (`workflow_success_rate`, `error_rate`, `limit_rate`, `trade_execution_rate`, `strategy_reject_rate`, `trade_win_rate`, `total_trades`, `wins`, `losses`, `total_pnl_usdt`, `avg_win_usdt`, `avg_loss_usdt`, `profit_factor`, `agent_output_quality`).
- Shared UI: `StatusBadge` (`@/components/run-status/StatusBadge`), `PositionProtection` + `ExecutionVisibility` (`@/components/projects/position-protection`), `ReadinessBadge` + `useTradingReadiness` (`@/components/projects/readiness-badge`).

**All trading proxy routes already exist** — no new API route files were needed in Phase D, and likely none for E/F (readiness + learning endpoints proxied already; verify before adding).

---

## 5. Phase D — what was implemented (DONE)

### Files created
- `src/lib/focused-runs.ts` — shared helpers (reason mappers, symbol extraction, detail href).
- `src/components/projects/trades-view.tsx` — `TradesView({ projectId, runs })`. Four react-query calls (`trading/executions`, `trading/positions`, `trading/journal` with `retry:false`, `trading/performance/summary`). Renders `ReadinessBadge` + mode, StatCards (Executions, Open Positions, Executed-trade Runs = `runs.filter(r => displayStatusOf(r) === "complete-trade").length`, Trade Win Rate from perf), executions list (`execution-submitted` pill: "Submitted to exchange" if `order_id` else "Simulated (no order id)"), positions list w/ `PositionProtection`, journal list. Win rate: `perf && perf.total_trades > 0 ? Math.round(perf.trade_win_rate)+"%" : "—"`. `data-testid="trades-view"`.
- `src/components/projects/rejected-view.tsx` — `RejectedView({ runs })`, filter `complete-reject`, neutral MUTED styling, `reject-reason` pill + `reject-run-link`. `data-testid="rejected-view"`.
- `src/components/projects/limits-view.tsx` — `LimitsView({ runs })`, `isLimitRun`, WARN/SAFE styling, `limit-reason` + `limit-health` ("Healthy safety behaviour" vs "Needs attention") + `limit-run-link`. `data-testid="limits-view"`.
- `src/components/projects/errors-view.tsx` — `ErrorsView({ runs })`, filter `isErrorRun`, danger styling, `suggestedFix(run)` category hints, `StatusBadge`, raw reason `<pre>`, `error-run-link`. `data-testid="errors-view"`.
- `src/components/projects/performance-view.tsx` — `PerformanceView({ projectId })`. Fetches `trading/performance/summary` + `runs/summary` (`retry:false`). Workflow rates prefer perf, fall back to runs/summary via `fromSummaryRate(key)` = `by_display_status[key]/terminal`. `workflowHealth = perf ? perf.workflow_success_rate : summary ? 100 - (fromSummaryRate("error") ?? 0) : null`. **Win Rate ONLY from perf**, never runs. Two StatCard groups (Workflow Metrics / Trading Metrics) + "How to read this" helper `<ul>`. `data-testid="performance-view"`.

> **Components take `{ projectId: string; runs: FocusedRun[] }` in the type but the
> view-only ones destructure just `{ runs }`** — keeps `projectId` in the prop
> contract (tests pass it) without an unused-var lint warning.

### Files modified
- `src/app/[locale]/(dashboard)/projects/[id]/page.tsx` — imported the 5 views; replaced Trades/Rejected/Limits/Performance placeholder shells with real views; replaced the ~50-line inline Errors block with `<ErrorsView>`. Learning/Settings remain placeholder shells. Legacy `#error-log → errors` alias and the Trade Floor legacy tab/route still work. Overview behavior unchanged.

### Tests created (29, all green)
- `src/lib/focused-runs.test.ts` (16) — reason mapping, healthy-vs-attention, symbol extraction, detail href.
- `src/components/projects/rejected-view.test.tsx` (3)
- `src/components/projects/limits-view.test.tsx` (3)
- `src/components/projects/errors-view.test.tsx` (3)
- `src/components/projects/trades-view.test.tsx` (2)
- `src/components/projects/performance-view.test.tsx` (2)

### Performance metric labels / formulas (as displayed)
- **Workflow Health** = `workflow_success_rate` (fallback `100 − error_rate`) — labeled "Workflow Health", explicitly NOT win rate.
- **Execution Rate** = `trade_execution_rate`; **Reject Rate** = `strategy_reject_rate`; **Error Rate** = `error_rate`; **Limit Rate** = `limit_rate` (each fallback = `by_display_status[key]/terminal`).
- **Win Rate** = `trade_win_rate` only when `total_trades > 0`, from backend summary (closed TradeJournal trades), never runs; "—" if unavailable.
- Realized PnL = `total_pnl_usdt`; Avg Win/Loss = `avg_win_usdt`/`avg_loss_usdt`; Profit Factor = `profit_factor`.
- Helper copy: Workflow Health ≠ Win Rate; rejected = intentional no-trade; limits = safety controls; Win Rate = closed trade-journal results.

### Phase D verification results
- 29 new tests pass.
- `npx vitest run src/lib src/components/projects` → **99 passed / 16 files** (no Phase A/C regressions).
- `npx tsc --noEmit` → **0 errors**.
- eslint on all new files → **0 errors / 0 warnings** (page.tsx retains 9 pre-existing unused-var warnings, untouched).
- Full suite `npx vitest run` → **131 passed, 1 failed**.

### ⚠️ Pre-existing unrelated failure (NOT Phase D)
`src/components/workboard/__tests__/RunCard.test.tsx > should render trigger name`
— `getByText("manual")` matches two elements because `RunCard.tsx` renders the
trigger both as the card title (when `workflow_name` empty) and as the trigger
pill. `RunCard.tsx` imports none of the Phase D files. Pre-existing; left as-is.

---

## 6. Phase E — Settings readiness panel (NEXT, on approval)

**Goal:** In-depth Settings tab showing trading readiness without exposing secrets.
- Source: `trading/readiness` (proxy exists) + `useTradingReadiness`/`ReadinessBadge` (Phase C).
- Show: credential **presence booleans** + env-var **name patterns** only — NEVER values.
- Likely items: exchange creds present?, mode (PAPER/DEMO/TESTNET/LIVE), kill-switch state, budget/risk caps configured?, required env vars present/missing list.
- Replace the Settings placeholder shell in `page.tsx` (`{tab === "settings" && ...}`).
- Reuse pixel-UI + readiness components; add `settings-view.tsx` + tests; keep guard pattern for any query mocks.

## 7. Phase F — Learning dashboard (LATER, on approval)

**Goal:** Surface learning/quality signals (e.g. `agent_output_quality`, strategy
adaptation). Source endpoints TBD — verify proxies exist before adding routes.
Replace the Learning placeholder shell (`{tab === "learning" && ...}`).

---

## 8. How to verify (run these before claiming done)

```bash
cd frontend
npx vitest run src/lib src/components/projects   # focused suite
npx tsc --noEmit                                  # type check
npx eslint <changed files>                        # lint changed files only
# (optional) npx vitest run                        # full suite — expect the 1 pre-existing RunCard failure
```

## 9. Deliverable format (the spec's required report shape)
When finishing a phase, report: 1) Files changed; 2) Views implemented; 3) Data
sources; 4) Filtering rules; 5) Performance metric labels/formulas; 6) Tests
added/updated; 7) Test results; 8) Confirmation later-phase work not done;
9) Confirmation no backend logic / validators / HAWK-SAGE prompts / DB schema /
DB data / orders touched.
