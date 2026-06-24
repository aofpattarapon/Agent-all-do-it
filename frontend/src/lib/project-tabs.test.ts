import { describe, expect, it } from "vitest";

import {
  DEFAULT_TAB,
  DETAIL_TABS,
  LEGACY_MENU,
  PRIMARY_MENU,
  resolveTabHash,
  tabToHash,
} from "./project-tabs";

describe("project-tabs taxonomy", () => {
  it("defaults to #overview when no hash is present", () => {
    expect(DEFAULT_TAB).toBe("overview");
    expect(resolveTabHash("")).toBe("overview");
    expect(resolveTabHash(null)).toBe("overview");
    expect(resolveTabHash(undefined)).toBe("overview");
  });

  it("resolves the explicit #overview hash", () => {
    expect(resolveTabHash("#overview")).toBe("overview");
    expect(resolveTabHash("overview")).toBe("overview");
  });

  it("keeps the legacy #agents deep link working", () => {
    expect(resolveTabHash("#agents")).toBe("agents");
    expect(resolveTabHash("agents")).toBe("agents");
  });

  it("aliases the legacy #error-log hash safely to errors", () => {
    expect(resolveTabHash("#error-log")).toBe("errors");
    expect(resolveTabHash("error-log")).toBe("errors");
  });

  it("redirects every legacy hash to its parent tab (no broken deep links)", () => {
    // Legacy surfaces are folded into a parent tab as in-page sections; the old
    // deep-link hash now resolves to that parent so existing links keep working.
    const redirects: Record<string, string> = {
      // Still folded into a parent as in-page sections.
      knowledge: "learning",
      // Navigable tabs (top-level or sub-menu) — resolve to themselves.
      handoffs: "handoffs",
      integrations: "integrations",
      secrets: "secrets",
      vault: "vault",
      workflows: "workflows",
      errors: "errors",
      "trade-floor": "trade-floor",
      workboard: "workboard",
      office: "office",
      schedules: "schedules",
      runs: "runs",
      rejected: "rejected",
      "limits-safety": "limits-safety",
    };
    for (const [legacy, parent] of Object.entries(redirects)) {
      expect(resolveTabHash(`#${legacy}`)).toBe(parent);
    }
  });

  it("falls back to the default tab for unknown hashes", () => {
    expect(resolveTabHash("#does-not-exist")).toBe("overview");
  });

  it("emits a clean (empty) hash for the default tab and #tab otherwise", () => {
    expect(tabToHash("overview")).toBe("");
    expect(tabToHash("agents")).toBe("#agents");
    expect(tabToHash("errors")).toBe("#errors");
  });

  it("exposes the full Phase C primary menu", () => {
    const labels = PRIMARY_MENU.map((m) => m.label);
    expect(labels).toEqual([
      "Overview",
      "Office",
      "Workboard",
      "Runs",
      "Trades",
      "Performance",
      "Learning",
      "Agents",
      "Schedules",
      "Settings",
    ]);
  });

  it("keeps the legacy surfaces in a secondary menu", () => {
    const tabs = LEGACY_MENU.map((m) => m.tab);
    for (const legacy of ["trade-floor", "workboard", "office", "handoffs", "integrations", "secrets", "vault"]) {
      expect(tabs).toContain(legacy);
    }
  });

  it("every menu tab is a registered DETAIL_TAB", () => {
    for (const item of [...PRIMARY_MENU, ...LEGACY_MENU]) {
      expect(DETAIL_TABS).toContain(item.tab);
    }
  });
});
