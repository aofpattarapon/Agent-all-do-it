"use client";

import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { PixelFrame, PixelNavButton } from "@/components/pixel-ui";
import { ProjectSectionShell } from "@/components/projects/ProjectSectionShell";

interface Handoff {
  id: string;
  project_id: string;
  run_id: string;
  from_agent_id: string | null;
  to_agent_id: string | null;
  status: string;
  summary: string;
  package_json: Record<string, unknown>;
  quality_gate_result: Record<string, unknown>;
  approved_by: string | null;
  approved_at: string | null;
  rejected_reason: string;
  created_at: string;
}

const FILTERS = ["all", "ready", "approved", "rejected", "sent", "received", "completed"] as const;
type Filter = (typeof FILTERS)[number];

export default function ProjectHandoffsView({
  projectId,
  embedded = false,
}: {
  projectId: string;
  embedded?: boolean;
}) {
  const [handoffs, setHandoffs] = useState<Handoff[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<Filter>("all");

  useEffect(() => {
    async function fetchHandoffs() {
      try {
        const data = await apiClient.get<{ items: Handoff[]; total: number }>(`/projects/${projectId}/handoffs`);
        setHandoffs(data.items);
      } catch {
        // fallback to empty if endpoint doesn't exist yet
      } finally {
        setLoading(false);
      }
    }
    fetchHandoffs();
  }, [projectId]);

  const filtered = filter === "all" ? handoffs : handoffs.filter((h) => h.status === filter);

  const statusPill = (status: string) => {
    const map: Record<string, string> = {
      draft: "pix-pill",
      ready: "pix-pill pix-running",
      approved: "pix-pill pix-completed",
      rejected: "pix-pill pix-failed",
      sent: "pix-pill pix-running",
      received: "pix-pill pix-completed",
      completed: "pix-pill pix-completed",
    };
    return map[status] || "pix-pill";
  };

  const content = (
    <>
      <PixelFrame tight>
        <div className="pix-greet">
          <div>
            <div className="pix-eyebrow">Handoff Center</div>
            <h2>Agent Handoffs</h2>
          </div>
        </div>
      </PixelFrame>

      {/* Filter bar */}
      <div className="pix-tabs">
        {FILTERS.map((f) => (
          <PixelNavButton
            key={f}
            icon={<span style={{ fontSize: 10 }}>•</span>}
            label={f.charAt(0).toUpperCase() + f.slice(1)}
            active={filter === f}
            onClick={() => setFilter(f)}
            badge={f === "all" ? handoffs.length : handoffs.filter((h) => h.status === f).length}
          />
        ))}
      </div>

      {loading ? (
        <PixelFrame variant="screen">
          <div className="pix-empty" style={{ color: "#9bdbaa" }}>Loading handoffs…</div>
        </PixelFrame>
      ) : filtered.length === 0 ? (
        <PixelFrame variant="screen">
          <div className="pix-empty" style={{ color: "#9bdbaa" }}>
            No handoffs yet. Handoffs are created automatically during workflow runs.
          </div>
        </PixelFrame>
      ) : (
        <div className="space-y-2">
          {filtered.map((h) => (
            <PixelFrame key={h.id} tight>
              <div className="pix-row" style={{ alignItems: "center" }}>
                <div className="min-w-0 space-y-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="pix-row-title">Handoff #{h.id.slice(0, 8)}</span>
                    <span className={statusPill(h.status)}>{h.status}</span>
                  </div>
                  <p className="pix-row-sub">{h.summary || "No summary"}</p>
                  <div className="pix-mono" style={{ fontSize: 12, color: "var(--pix-ink-soft)" }}>
                    {h.from_agent_id ? `From: ${h.from_agent_id.slice(0, 8)}` : "System"}
                    {" → "}
                    {h.to_agent_id ? `To: ${h.to_agent_id.slice(0, 8)}` : "Unassigned"}
                    {" · "}
                    {new Date(h.created_at).toLocaleString()}
                  </div>
                </div>
              </div>
            </PixelFrame>
          ))}
        </div>
      )}
    </>
  );

  if (embedded) return <div className="space-y-4">{content}</div>;

  return <ProjectSectionShell projectId={projectId} activeSection="handoffs">{content}</ProjectSectionShell>;
}
