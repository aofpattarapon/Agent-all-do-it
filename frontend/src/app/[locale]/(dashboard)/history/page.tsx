"use client";

import { useMemo, useState } from "react";
import { format } from "date-fns";
import { Download } from "lucide-react";
import { useConsoleData, type EnrichedRun, sortByRecency } from "@/components/console/use-console-data";
import { PixelFrame, SectionLabel } from "@/components/pixel-ui";

function duration(run: EnrichedRun): string {
  if (!run.started_at || !run.finished_at) return "—";
  const diff = new Date(run.finished_at).getTime() - new Date(run.started_at).getTime();
  if (diff < 1000) return "<1s";
  const secs = Math.floor(diff / 1000);
  if (secs < 60) return `${secs}s`;
  return `${Math.floor(secs / 60)}m ${secs % 60}s`;
}

const STATUS_OPTIONS = ["all", "completed", "failed", "running", "queued", "pending"];

export default function HistoryPage() {
  const { projects, allRuns } = useConsoleData();
  const [projectFilter, setProjectFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");

  const rows = useMemo(() => {
    let runs = allRuns;
    if (projectFilter !== "all") runs = runs.filter((r) => r.projectId === projectFilter);
    if (statusFilter !== "all") runs = runs.filter((r) => r.status === statusFilter);
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
            <select className="pix-select" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              {STATUS_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {s === "all" ? "All Status" : s}
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
                        <span className={"pix-pill pix-" + run.status}>{run.status}</span>
                      </td>
                      <td>{duration(run)}</td>
                      <td>
                        {run.status === "completed" ? (
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
