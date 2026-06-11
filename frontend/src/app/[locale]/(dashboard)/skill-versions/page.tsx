"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, apiClient } from "@/lib/api-client";
import { PixelButton, PixelFrame, SectionLabel } from "@/components/pixel-ui";
import { useAuthStore } from "@/stores";

interface Skill {
  id: string;
  name: string;
  category: string;
  is_active: boolean;
}

interface SkillVersion {
  id: string;
  skill_id: string;
  version_number: number;
  prompt_fragment: string;
  status: "active" | "canary" | "rollback_ready" | "archived";
  canary_percentage: number;
  winrate: number | null;
  sample_size: number;
  approved_by: string | null;
  notes: string | null;
  created_at: string;
}

interface SkillVersionsResponse {
  items: SkillVersion[];
  total: number;
}

const STATUS_COLOR: Record<SkillVersion["status"], string> = {
  active: "#6fe08c",
  canary: "#e7b53c",
  rollback_ready: "#60a5fa",
  archived: "#6b7280",
};

function StatusBadge({ status }: { status: SkillVersion["status"] }) {
  return (
    <span
      className="pix-mono"
      style={{
        fontSize: 12,
        padding: "1px 7px",
        border: `2px solid ${STATUS_COLOR[status]}`,
        color: STATUS_COLOR[status],
        borderRadius: 2,
      }}
    >
      {status}
    </span>
  );
}

function VersionRow({
  skillId,
  version,
  isAdmin,
}: {
  skillId: string;
  version: SkillVersion;
  isAdmin: boolean;
}) {
  const queryClient = useQueryClient();

  const approveMutation = useMutation({
    mutationFn: () => apiClient.post(`/skills/${skillId}/versions/${version.id}/approve`, {}),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["skill-versions", skillId] });
    },
  });

  const rollbackMutation = useMutation({
    mutationFn: () => apiClient.post(`/skills/${skillId}/versions/${version.id}/rollback`, {}),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["skill-versions", skillId] });
    },
  });

  return (
    <tr style={{ borderBottom: "1px solid #4a423840" }}>
      <td style={{ padding: "5px 8px" }} className="pix-mono">
        v{version.version_number}
      </td>
      <td style={{ padding: "5px 8px" }}>
        <StatusBadge status={version.status} />
      </td>
      <td style={{ padding: "5px 8px" }} className="pix-mono">
        {version.canary_percentage > 0 ? `${version.canary_percentage}%` : "—"}
      </td>
      <td style={{ padding: "5px 8px" }} className="pix-mono">
        {version.winrate !== null ? `${(version.winrate * 100).toFixed(1)}%` : "—"}
      </td>
      <td style={{ padding: "5px 8px" }} className="pix-mono">
        {version.sample_size}
      </td>
      <td style={{ padding: "5px 8px" }} className="pix-mono">
        {version.approved_by ?? "—"}
      </td>
      <td
        className="pix-mono"
        style={{ padding: "5px 8px", fontSize: 12, color: "var(--pix-ink-soft)" }}
      >
        {version.notes?.slice(0, 60) ?? "—"}
      </td>
      <td style={{ padding: "5px 8px" }}>
        <div style={{ display: "flex", gap: 6 }}>
          {isAdmin && version.status === "canary" && (
            <PixelButton
              variant="green"
              onClick={() => approveMutation.mutate()}
              disabled={approveMutation.isPending}
            >
              {approveMutation.isPending ? "…" : "Approve"}
            </PixelButton>
          )}
          {isAdmin && version.status === "rollback_ready" && (
            <PixelButton
              onClick={() => rollbackMutation.mutate()}
              disabled={rollbackMutation.isPending}
            >
              {rollbackMutation.isPending ? "…" : "Rollback"}
            </PixelButton>
          )}
        </div>
      </td>
    </tr>
  );
}

function SkillAccordion({ skill, isAdmin }: { skill: Skill; isAdmin: boolean }) {
  const [open, setOpen] = useState(false);

  const versionsQuery = useQuery<SkillVersionsResponse, ApiError>({
    queryKey: ["skill-versions", skill.id],
    queryFn: () => apiClient.get(`/skills/${skill.id}/versions`),
    enabled: open,
  });

  const versions = versionsQuery.data?.items ?? [];

  return (
    <div style={{ borderBottom: "1px solid var(--pix-frame)" }}>
      <button
        onClick={() => setOpen((value) => !value)}
        style={{
          width: "100%",
          textAlign: "left",
          background: "transparent",
          border: "none",
          padding: "10px 12px",
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          gap: 10,
          fontFamily: "VT323, monospace",
          fontSize: 16,
          color: "var(--pix-ink)",
        }}
      >
        <span>{open ? "▼" : "▶"}</span>
        <span style={{ flex: 1 }}>{skill.name}</span>
        <span className="pix-mono" style={{ fontSize: 12, color: "var(--pix-ink-soft)" }}>
          {skill.category}
        </span>
        {!skill.is_active && (
          <span className="pix-mono" style={{ fontSize: 11, color: "#6b7280" }}>
            inactive
          </span>
        )}
      </button>

      {open && (
        <div style={{ padding: "0 12px 12px" }}>
          {versionsQuery.isLoading ? (
            <div className="pix-empty">Loading versions…</div>
          ) : versionsQuery.error ? (
            <div className="pix-empty" style={{ color: "#df5b53", fontSize: 13 }}>
              {versionsQuery.error.message}
            </div>
          ) : versions.length === 0 ? (
            <div className="pix-empty" style={{ fontSize: 13 }}>
              No versions yet.
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table
                style={{
                  width: "100%",
                  borderCollapse: "collapse",
                  fontFamily: "VT323, monospace",
                  fontSize: 14,
                }}
              >
                <thead>
                  <tr style={{ borderBottom: "2px solid var(--pix-frame)", color: "var(--pix-ink-soft)" }}>
                    <th style={{ textAlign: "left", padding: "4px 8px" }}>Version</th>
                    <th style={{ textAlign: "left", padding: "4px 8px" }}>Status</th>
                    <th style={{ textAlign: "left", padding: "4px 8px" }}>Canary %</th>
                    <th style={{ textAlign: "left", padding: "4px 8px" }}>Winrate</th>
                    <th style={{ textAlign: "left", padding: "4px 8px" }}>Sample Size</th>
                    <th style={{ textAlign: "left", padding: "4px 8px" }}>Approved By</th>
                    <th style={{ textAlign: "left", padding: "4px 8px" }}>Notes</th>
                    <th style={{ textAlign: "left", padding: "4px 8px" }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {versions.map((version) => (
                    <VersionRow
                      key={version.id}
                      skillId={skill.id}
                      version={version}
                      isAdmin={isAdmin}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function SkillVersionsPage() {
  const { user } = useAuthStore();
  const isAdmin = user?.role === "admin";

  const skillsQuery = useQuery<Skill[], ApiError>({
    queryKey: ["skills"],
    queryFn: () => apiClient.get("/skills"),
  });

  const skills = skillsQuery.data ?? [];

  return (
    <>
      <PixelFrame tight>
        <div className="pix-eyebrow">Hub Management</div>
        <h2 style={{ margin: 0 }}>Skill Versions</h2>
        <div className="pix-mono" style={{ fontSize: 13, marginTop: 4, color: "var(--pix-ink-soft)" }}>
          Canary deployments for skill prompt fragments. Human approval is required before promotion.
        </div>
      </PixelFrame>

      {!isAdmin && (
        <PixelFrame>
          <div className="pix-mono" style={{ color: "#e7b53c", fontSize: 13 }}>
            Approve and rollback actions are visible to admins only.
          </div>
        </PixelFrame>
      )}

      <PixelFrame>
        <SectionLabel>Skills · {skills.length} total</SectionLabel>
        {skillsQuery.isLoading ? (
          <div className="pix-empty">Loading skills…</div>
        ) : skillsQuery.error ? (
          <div className="pix-empty" style={{ color: "#df5b53" }}>
            {skillsQuery.error.message}
          </div>
        ) : skills.length === 0 ? (
          <div className="pix-empty">No skills found. Seed the skill catalog first.</div>
        ) : (
          <div>
            {skills.map((skill) => (
              <SkillAccordion key={skill.id} skill={skill} isAdmin={isAdmin} />
            ))}
          </div>
        )}
      </PixelFrame>
    </>
  );
}
