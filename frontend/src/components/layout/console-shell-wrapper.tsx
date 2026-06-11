"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { ConsoleShell } from "@/components/console/ConsoleShell";
import { useConsolePrefs } from "@/components/console/use-console-prefs";

/** Pathnames (locale-stripped) that should render full-bleed without the sidebar. */
const FULL_BLEED_PATTERNS = ["/workflows/", "/editor"];

function isFullBleed(pathname: string): boolean {
  // Strip leading locale segment e.g. /en/... → /...
  const stripped = pathname.replace(/^\/[a-z]{2}(?=\/|$)/, "") || "/";
  return FULL_BLEED_PATTERNS.some((pattern) => stripped.includes(pattern));
}

export function ConsoleShellWrapper({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { prefs } = useConsolePrefs();

  if (isFullBleed(pathname)) {
    return <>{children}</>;
  }

  return (
    <ConsoleShell
      showTeam={prefs.showTeam}
      showActivity={prefs.showActivity}
      animations={prefs.animations}
    >
      {children}
    </ConsoleShell>
  );
}
