"use client";

import { useCallback, useEffect, useState } from "react";

export type TimeRange = "all" | "today" | "week" | "month";

export interface ConsolePrefs {
  pixelTheme: boolean;
  animations: boolean;
  eveningLight: boolean;
  defaultRange: TimeRange;
  showTeam: boolean;
  showActivity: boolean;
  toastOnComplete: boolean;
  toastOnFailed: boolean;
}

export const DEFAULT_PREFS: ConsolePrefs = {
  pixelTheme: true,
  animations: true,
  eveningLight: false,
  defaultRange: "week",
  showTeam: true,
  showActivity: true,
  toastOnComplete: true,
  toastOnFailed: true,
};

const STORAGE_KEY = "pdConsolePrefs";

function readPrefs(): ConsolePrefs {
  if (typeof window === "undefined") return DEFAULT_PREFS;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_PREFS;
    return { ...DEFAULT_PREFS, ...(JSON.parse(raw) as Partial<ConsolePrefs>) };
  } catch {
    return DEFAULT_PREFS;
  }
}

/** localStorage-backed console preferences (key: pdConsolePrefs). */
export function useConsolePrefs() {
  const [prefs, setPrefs] = useState<ConsolePrefs>(DEFAULT_PREFS);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    setPrefs(readPrefs());
    setLoaded(true);
  }, []);

  const update = useCallback(<K extends keyof ConsolePrefs>(key: K, value: ConsolePrefs[K]) => {
    setPrefs((prev) => {
      const next = { ...prev, [key]: value };
      try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      } catch {
        // ignore quota / unavailable storage
      }
      return next;
    });
  }, []);

  const reset = useCallback(() => {
    setPrefs(DEFAULT_PREFS);
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(DEFAULT_PREFS));
    } catch {
      // ignore
    }
  }, []);

  return { prefs, update, reset, loaded };
}
