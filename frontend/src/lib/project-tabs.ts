// Canonical project tab taxonomy + hash routing (Phase C menu shell).
//
// Adds the new top-level menu (Overview / Runs / Trades / Rejected / Limits &
// Safety / Errors / Performance / Learning / Agents / Settings) WITHOUT breaking
// any existing route or deep-link hash. Every legacy tab stays in `DETAIL_TABS`
// so its `#hash` keeps resolving, and `HASH_ALIASES` maps old hashes that were
// renamed (e.g. `#error-log` -> `errors`).

export const DETAIL_TABS = [
  // Primary top-level menu (Phase C).
  "overview",
  "runs",
  "trades",
  "rejected",
  "limits-safety",
  "errors",
  "performance",
  "learning",
  "agents",
  "settings",
  // Existing core tabs — still reachable by hash / legacy menu.
  "knowledge",
  "workflows",
  "schedules",
  // Legacy tabs — kept working, hashes preserved.
  "trade-floor",
  "workboard",
  "office",
  "handoffs",
  "integrations",
  "secrets",
  "vault",
  "error-log",
] as const;

export type DetailTab = (typeof DETAIL_TABS)[number];

// Overview is the new default project tab (replaces the old `agents` default).
export const DEFAULT_TAB: DetailTab = "overview";

// Legacy hash aliases — old deep links keep working, mapped to the canonical tab.
export const HASH_ALIASES: Record<string, DetailTab> = {
  "error-log": "errors",
  // Surfaces still folded into a parent tab as in-page sections — old deep-link
  // hashes redirect to that parent so existing links keep working.
  knowledge: "learning",
  // office / workboard / schedules / trade-floor / errors / handoffs / workflows
  // / integrations / secrets / vault are now navigable tabs (top-level or
  // sub-menu) — their hashes resolve to themselves.
};

const TAB_SET = new Set<string>(DETAIL_TABS);

/** Resolve a raw hash (with or without leading `#`) to a canonical tab. Pure + SSR-safe. */
export function resolveTabHash(raw: string | null | undefined): DetailTab {
  const value = (raw ?? "").replace(/^#/, "");
  if (!value) return DEFAULT_TAB;
  const aliased = HASH_ALIASES[value] ?? value;
  return TAB_SET.has(aliased) ? (aliased as DetailTab) : DEFAULT_TAB;
}

/** The URL hash for a tab (empty string for the default tab → clean URL). */
export function tabToHash(tab: DetailTab): string {
  return tab === DEFAULT_TAB ? "" : `#${tab}`;
}

export interface ProjectMenuItem {
  tab: DetailTab;
  label: string;
}

// Primary top-level menu in display order. Office / Workboard / Schedules are
// standalone bar buttons again; Runs and Trades expand into themed sub-rows
// (see RUNS_SUBTABS / TRADES_SUBTABS) so Rejected, Limits & Safety and Trade
// Floor live under their parent instead of cluttering the bar.
export const PRIMARY_MENU: readonly ProjectMenuItem[] = [
  { tab: "overview", label: "Overview" },
  { tab: "office", label: "Office" },
  { tab: "workboard", label: "Workboard" },
  { tab: "runs", label: "Runs" },
  { tab: "trades", label: "Trades" },
  { tab: "performance", label: "Performance" },
  { tab: "learning", label: "Learning" },
  { tab: "agents", label: "Agents" },
  { tab: "schedules", label: "Schedules" },
  { tab: "settings", label: "Settings" },
];

// Sub-menu groups: clicking the parent bar button reveals a themed sub-row that
// switches among these tabs (the parent itself is the first/"all" entry).
export const RUNS_SUBTABS: readonly ProjectMenuItem[] = [
  { tab: "runs", label: "All Runs" },
  { tab: "rejected", label: "Rejected" },
  { tab: "limits-safety", label: "Limits & Safety" },
  { tab: "errors", label: "Errors" },
];

export const TRADES_SUBTABS: readonly ProjectMenuItem[] = [
  { tab: "trades", label: "Trades — executed orders only" },
  { tab: "trade-floor", label: "Trade Floor" },
];

export const AGENTS_SUBTABS: readonly ProjectMenuItem[] = [
  { tab: "agents", label: "Agents" },
  { tab: "handoffs", label: "Handoff Center" },
];

export const SETTINGS_SUBTABS: readonly ProjectMenuItem[] = [
  { tab: "settings", label: "Settings" },
  { tab: "workflows", label: "Workflows" },
  { tab: "integrations", label: "Integrations" },
  { tab: "secrets", label: "Secrets" },
  { tab: "vault", label: "Vault" },
];

const RUNS_GROUP = new Set<DetailTab>(RUNS_SUBTABS.map((s) => s.tab));
const TRADES_GROUP = new Set<DetailTab>(TRADES_SUBTABS.map((s) => s.tab));
const AGENTS_GROUP = new Set<DetailTab>(AGENTS_SUBTABS.map((s) => s.tab));
const SETTINGS_GROUP = new Set<DetailTab>(SETTINGS_SUBTABS.map((s) => s.tab));

/** Map any tab to the top-level bar button that should appear active for it. */
export function barParentOf(tab: DetailTab): DetailTab {
  if (RUNS_GROUP.has(tab)) return "runs";
  if (TRADES_GROUP.has(tab)) return "trades";
  if (AGENTS_GROUP.has(tab)) return "agents";
  if (SETTINGS_GROUP.has(tab)) return "settings";
  return tab;
}

// Secondary / legacy menu — existing surfaces kept reachable, hashes preserved.
export const LEGACY_MENU: readonly ProjectMenuItem[] = [
  { tab: "knowledge", label: "Knowledge" },
  { tab: "workflows", label: "Workflows" },
  { tab: "schedules", label: "Schedules" },
  { tab: "trade-floor", label: "Trade Floor" },
  { tab: "workboard", label: "Workboard" },
  { tab: "office", label: "Office" },
  { tab: "handoffs", label: "Handoffs" },
  { tab: "integrations", label: "Integrations" },
  { tab: "secrets", label: "Secrets" },
  { tab: "vault", label: "Vault" },
];
