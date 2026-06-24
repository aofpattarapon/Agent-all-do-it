"use client";

import { useMemo, useState } from "react";
import { format } from "date-fns";
import { Download } from "lucide-react";
import { useConsoleData, type EnrichedRun, sortByRecency } from "@/components/console/use-console-data";
import { PixelFrame, SectionLabel } from "@/components/pixel-ui";
import { StatusBadge } from "@/components/run-status/StatusBadge";
import { displayStatusOf, type DisplayStatus } from "@/lib/run-status";

function duration(run: EnrichedRun): string {
  if (!run.started_at || !run.finished_at) return "—";
  const diff = new Date(run.finished_at).getTime() - new Date(run.started_at).getTime();
  if (diff < 1000) return "<1s";
  const secs = Math.floor(diff / 1000);
  if (secs < 60) return `${secs}s`;
  return `${Math.floor(secs / 60)}m ${secs % 60}s`;
}

const STATUS_OPTIONS: { key: DisplayStatus | "all"; label: string }[] = [
  { key: "all", label: "All Status" },
  { key: "active", label: "Active" },
  { key: "complete-trade", label: "Trade" },
  { key: "complete-reject", label: "Rejected" },
  { key: "limit", label: "Limit" },
  { key: "error", label: "Error" },
];

export default function HistoryPage() {
  const { projects, allRuns } = useConsoleData();
  const [projectFilter, setProjectFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState<DisplayStatus | "all">("all");

  const rows = useMemo(() => {
    let runs = allRuns;
    if (projectFilter !== "all") runs = runs.filter((r) => r.projectId === projectFilter);
    if (statusFilter !== "all") runs = runs.filter((r) => displayStatusOf(r) === statusFilter);
    return sortByRecency(runs);
  }, [allRuns, projectFilter, statusFilter]);

  return (
    <>
      <PixelFrame tight>
        <div className="pix-greet">
          <div>
            <div className="pix-eyebrow">Console</div>
            <h2>📜 History</h2>
          </div>
          <div className="pix-filters">
            <select
              className="pix-select"
              value={projectFilter}
              onChange={(e) => setProjectFilter(e.target.value)}
            >
              <option value="all">All Projects</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
            <select
              className="pix-select"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as DisplayStatus | "all")}
            >
              {STATUS_OPTIONS.map((s) => (
                <option key={s.key} value={s.key}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      </PixelFrame>

      <PixelFrame>
        <SectionLabel>Runs · {rows.length}</SectionLabel>
        {rows.length === 0 ? (
          <div className="pix-empty">No runs match these filters yet.</div>
        ) : (
          <div className="pix-table-wrap">
            <table className="pix-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Project</th>
                  <th>Workflow / Trigger</th>
                  <th>Status</th>
                  <th>Duration</th>
                  <th>Output</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((run) => {
                  const ts = run.started_at ?? run.finished_at;
                  return (
                    <tr key={run.id}>
                      <td className="pix-muted">{ts ? format(new Date(ts), "MMM d, HH:mm") : "—"}</td>
                      <td>{run.projectName}</td>
                      <td>{run.workflow_name ?? run.trigger ?? "manual"}</td>
                      <td>
                        <StatusBadge run={run} />
                      </td>
                      <td>{duration(run)}</td>
                      <td>
                        {displayStatusOf(run) !== "active" && displayStatusOf(run) !== "error" ? (
                          <a
                            className="pix-link"
                            href={`/api/projects/${run.projectId}/runs/${run.id}/download?format=markdown`}
                            download
                            style={{ display: "inline-flex", alignItems: "center", gap: 4 }}
                          >
                            <Download size={13} /> .md
                          </a>
                        ) : (
                          <span className="pix-muted">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </PixelFrame>
    </>
  );
}
