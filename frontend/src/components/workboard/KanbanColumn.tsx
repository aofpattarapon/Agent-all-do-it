"use client";

import { PixelFrame, SectionLabel } from "@/components/pixel-ui";
import { cn } from "@/lib/utils";
import type { EnrichedRun } from "@/components/console/use-console-data";
import { RunCard } from "./RunCard";

export interface KanbanColumnProps {
  label: string;
  color: "gray" | "blue" | "yellow" | "red" | "green";
  runs: EnrichedRun[];
  onAction: (action: "approve" | "reject" | "retry" | "cancel" | "override-approve", runId: string, projectId: string) => void;
}

const badgeColorClass: Record<string, string> = {
  gray: "bg-gray-200 text-gray-700",
  blue: "bg-blue-100 text-blue-700",
  yellow: "bg-amber-100 text-amber-700",
  red: "bg-red-100 text-red-700",
  green: "bg-green-100 text-green-700",
};

const borderColorClass: Record<string, string> = {
  gray: "border-gray-300",
  blue: "border-blue-300",
  yellow: "border-amber-300",
  red: "border-red-300",
  green: "border-green-300",
};

export function KanbanColumn({ label, color, runs, onAction }: KanbanColumnProps) {
  return (
    <div className="flex min-w-[280px] flex-1 flex-col">
      <PixelFrame variant="parchment" className={cn("flex h-full flex-col border-2", borderColorClass[color])}>
        {/* Header */}
        <div className="flex items-center justify-between px-3 py-2">
          <SectionLabel>{label}</SectionLabel>
          <span
            className={cn("rounded px-2 py-0.5 text-sm", badgeColorClass[color])}
            style={{ fontFamily: '"VT323", monospace' }}
          >
            {runs.length}
          </span>
        </div>

        {/* Cards */}
        <div className="flex-1 overflow-y-auto px-2 pb-2" style={{ maxHeight: "calc(100vh - 200px)" }}>
          {runs.length === 0 ? (
            <div className="py-8 text-center text-sm" style={{ fontFamily: '"VT323", monospace', color: "var(--pix-muted)" }}>
              No runs
            </div>
          ) : (
            runs.map((run) => (
              <RunCard key={run.id} run={run} onAction={onAction} />
            ))
          )}
        </div>
      </PixelFrame>
    </div>
  );
}
