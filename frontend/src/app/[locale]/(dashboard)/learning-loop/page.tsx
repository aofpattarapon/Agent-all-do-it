"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ApiError, apiClient } from "@/lib/api-client";
import { PixelButton, PixelFrame, SectionLabel, StatCard } from "@/components/pixel-ui";
import { useAuthStore } from "@/stores";

interface Skill {
  id: string;
  name: string;
  category: string;
}

interface SkillVersion {
  id: string;
  skill_id: string;
  version_number: number;
  status: "active" | "canary" | "rollback_ready" | "archived";
  winrate: number | null;
  sample_size: number;
  created_at: string;
}

interface SkillVersionsResponse {
  items: SkillVersion[];
}

interface TrainerStatus {
  last_run: string | null;
  skills_evaluated: number;
  versions_created: number;
}

const DEFAULT_TRAINER_STATUS: TrainerStatus = {
  last_run: null,
  skills_evaluated: 0,
  versions_created: 0,
};

function WinrateMiniChart({ versions, chartId }: { versions: SkillVersion[]; chartId: string }) {
  const chartData = versions
    .filter((version) => version.winrate !== null)
    .sort((left, right) => left.version_number - right.version_number)
    .map((version) => ({
      label: `v${version.version_number}`,
      winrate: Math.round((version.winrate ?? 0) * 100),
    }));

  if (chartData.length < 2) return null;

  return (
    <div style={{ height: 60, marginTop: 6 }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={chartData} margin={{ top: 2, right: 2, left: -30, bottom: 0 }}>
          <defs>
            <linearGradient id={chartId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#6fe08c" stopOpacity={0.4} />
              <stop offset="100%" stopColor="#6fe08c" stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="label"
            tick={{ fill: "#9bdbaa", fontSize: 10, fontFamily: "VT323, monospace" }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis hide domain={[0, 100]} />
          <Tooltip
            formatter={(value) => [`${Number(value).toFixed(1)}%`, "winrate"]}
            contentStyle={{
              background: "#0e2118",
              border: "2px solid #2e1c0f",
              fontFamily: "VT323, monospace",
              fontSize: 13,
            }}
          />
          <Area
            type="monotone"
            dataKey="winrate"
            stroke="#6fe08c"
            fill={`url(#${chartId})`}
            strokeWidth={2}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function PendingApprovalRow({
  skill,
  version,
  activeWinrate,
  isAdmin,
}: {
  skill: Skill;
  version: SkillVersion;
  activeWinrate: number | null;
  isAdmin: boolean;
}) {
  const queryClient = useQueryClient();
  const delta =
    version.winrate !== null && activeWinrate !== null ? version.winrate - activeWinrate : null;

  const approveMutation = useMutation({
    mutationFn: () => apiClient.post(`/skills/${skill.id}/versions/${version.id}/approve`, {}),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["skill-versions", skill.id] });
    },
  });

  const archiveMutation = useMutation({
    mutationFn: () => apiClient.delete(`/skills/${skill.id}/versions/${version.id}`),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["skill-versions", skill.id] });
    },
  });

  return (
    <tr style={{ borderBottom: "1px solid #4a423840" }}>
      <td style={{ padding: "6px 8px" }} className="pix-mono">
        {skill.name}
      </td>
      <td style={{ padding: "6px 8px" }} className="pix-mono">
        v{version.version_number}
      </td>
      <td style={{ padding: "6px 8px" }} className="pix-mono">
        {version.winrate !== null ? `${(version.winrate * 100).toFixed(1)}%` : "—"}
      </td>
      <td
        className="pix-mono"
        style={{
          padding: "6px 8px",
          color: delta !== null ? (delta > 0 ? "#6fe08c" : "#df5b53") : undefined,
        }}
      >
        {delta !== null ? `${delta > 0 ? "+" : ""}${(delta * 100).toFixed(1)}%` : "—"}
      </td>
      <td style={{ padding: "6px 8px" }} className="pix-mono">
        {version.sample_size}
      </td>
      {isAdmin && (
        <td style={{ padding: "6px 8px" }}>
          <div style={{ display: "flex", gap: 6 }}>
            <PixelButton
              variant="green"
              onClick={() => approveMutation.mutate()}
              disabled={approveMutation.isPending}
            >
              {approveMutation.isPending ? "…" : "Approve"}
            </PixelButton>
            <PixelButton onClick={() => archiveMutation.mutate()} disabled={archiveMutation.isPending}>
              {archiveMutation.isPending ? "…" : "Archive"}
            </PixelButton>
          </div>
        </td>
      )}
    </tr>
  );
}

export default function LearningLoopPage() {
  const { user } = useAuthStore();
  const isAdmin = user?.role === "admin";
  const [trainerStatus, setTrainerStatus] = useState<TrainerStatus>(DEFAULT_TRAINER_STATUS);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem("learning-loop-trainer-status");
      if (!raw) return;
      const parsed = JSON.parse(raw) as Partial<TrainerStatus>;
      setTrainerStatus({
        last_run: parsed.last_run ?? null,
        skills_evaluated: parsed.skills_evaluated ?? 0,
        versions_created: parsed.versions_created ?? 0,
      });
    } catch {
      setTrainerStatus(DEFAULT_TRAINER_STATUS);
    }
  }, []);

  const skillsQuery = useQuery<Skill[], ApiError>({
    queryKey: ["skills"],
    queryFn: () => apiClient.get("/skills"),
  });

  const skills = skillsQuery.data ?? [];

  const versionQueries = useQueries({
    queries: skills.map((skill) => ({
      queryKey: ["skill-versions", skill.id],
      queryFn: () => apiClient.get<SkillVersionsResponse>(`/skills/${skill.id}/versions`),
      enabled: skills.length > 0,
    })),
  });

  const skillVersionEntries = useMemo(
    () =>
      skills.map((skill, index) => ({
        skill,
        query: versionQueries[index],
        versions: versionQueries[index]?.data?.items ?? [],
      })),
    [skills, versionQueries],
  );

  const pendingApprovals = useMemo(() => {
    return skillVersionEntries.flatMap(({ skill, versions }) => {
      const activeVersion = versions.find((version) => version.status === "active");
      return versions
        .filter((version) => version.status === "canary" && version.sample_size >= 50)
        .map((version) => ({
          skill,
          version,
          activeWinrate: activeVersion?.winrate ?? null,
        }));
    });
  }, [skillVersionEntries]);

  const recentActivity = useMemo(() => {
    return skillVersionEntries
      .flatMap(({ skill, versions }) =>
        versions.map((version) => ({
          ...version,
          skillName: skill.name,
        })),
      )
      .sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime())
      .slice(0, 10);
  }, [skillVersionEntries]);

  const totalActive = skillVersionEntries.reduce(
    (total, entry) => total + entry.versions.filter((version) => version.status === "active").length,
    0,
  );

  const totalCanaries = skillVersionEntries.reduce(
    (total, entry) => total + entry.versions.filter((version) => version.status === "canary").length,
    0,
  );

  return (
    <>
      <PixelFrame tight>
        <div className="pix-eyebrow">Hub Management</div>
        <h2 style={{ margin: 0 }}>Learning Loop</h2>
        <div className="pix-mono" style={{ fontSize: 13, marginTop: 4, color: "var(--pix-ink-soft)" }}>
          Daily trainer generates improved skill fragments. Canaries need human approval before promotion.
        </div>
      </PixelFrame>

      <div className="pix-grid-4">
        <StatCard label="Skills" value={skills.length} icon="🧠" sub="tracked" />
        <StatCard label="Active Versions" value={totalActive} icon="✅" />
        <StatCard label="Pending Canaries" value={totalCanaries} icon="🐤" sub="awaiting review" />
        <StatCard label="Pending Approvals" value={pendingApprovals.length} icon="⏸" sub="50+ samples" />
      </div>

      <div className="pix-grid-4">
        <StatCard
          label="Trainer Last Run"
          value={
            trainerStatus.last_run ? new Date(trainerStatus.last_run).toLocaleString() : "No runs yet"
          }
          icon="🕒"
        />
        <StatCard label="Skills Evaluated" value={trainerStatus.skills_evaluated} icon="📚" />
        <StatCard label="Versions Created" value={trainerStatus.versions_created} icon="🧪" />
        <StatCard label="Status Source" value="local mock" icon="ℹ️" sub="until API exists" />
      </div>

      <PixelFrame>
        <SectionLabel>Pending Approvals · {pendingApprovals.length}</SectionLabel>
        {pendingApprovals.length === 0 ? (
          <div className="pix-empty">No canary versions ready for review yet.</div>
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
                  <th style={{ textAlign: "left", padding: "4px 8px" }}>Skill</th>
                  <th style={{ textAlign: "left", padding: "4px 8px" }}>Version</th>
                  <th style={{ textAlign: "left", padding: "4px 8px" }}>Winrate</th>
                  <th style={{ textAlign: "left", padding: "4px 8px" }}>vs Active</th>
                  <th style={{ textAlign: "left", padding: "4px 8px" }}>Samples</th>
                  {isAdmin && <th style={{ textAlign: "left", padding: "4px 8px" }}>Actions</th>}
                </tr>
              </thead>
              <tbody>
                {pendingApprovals.map(({ skill, version, activeWinrate }) => (
                  <PendingApprovalRow
                    key={version.id}
                    skill={skill}
                    version={version}
                    activeWinrate={activeWinrate}
                    isAdmin={isAdmin}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </PixelFrame>

      <PixelFrame variant="screen">
        <SectionLabel>
          <span style={{ color: "#9bdbaa" }}>Winrate Trends by Skill</span>
        </SectionLabel>
        {skillsQuery.isLoading ? (
          <div className="pix-empty" style={{ color: "#9bdbaa" }}>
            Loading…
          </div>
        ) : skillsQuery.error ? (
          <div className="pix-empty" style={{ color: "#df5b53" }}>
            {skillsQuery.error.message}
          </div>
        ) : (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
              gap: 16,
            }}
          >
            {skillVersionEntries.map(({ skill, versions }) => (
              <div key={skill.id}>
                <div className="pix-mono" style={{ fontSize: 13, color: "#9bdbaa", marginBottom: 2 }}>
                  {skill.name}
                </div>
                <WinrateMiniChart versions={versions} chartId={`winrate-${skill.id}`} />
              </div>
            ))}
          </div>
        )}
      </PixelFrame>

      <PixelFrame>
        <SectionLabel>Recent Version Activity</SectionLabel>
        {recentActivity.length === 0 ? (
          <div className="pix-empty">No version activity yet.</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {recentActivity.map((version) => (
              <div
                key={version.id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  fontFamily: "VT323, monospace",
                  fontSize: 14,
                  padding: "4px 0",
                  borderBottom: "1px solid #4a423840",
                }}
              >
                <span
                  style={{
                    color:
                      {
                        active: "#6fe08c",
                        canary: "#e7b53c",
                        rollback_ready: "#60a5fa",
                        archived: "#6b7280",
                      }[version.status] ?? "#9ca3af",
                    minWidth: 10,
                  }}
                >
                  ●
                </span>
                <span style={{ flex: 1 }}>{version.skillName}</span>
                <span style={{ color: "var(--pix-gold)" }}>v{version.version_number}</span>
                <span style={{ color: "var(--pix-ink-soft)" }}>{version.status}</span>
                <span style={{ color: "var(--pix-ink-soft)", fontSize: 12 }}>
                  {new Date(version.created_at).toLocaleDateString()}
                </span>
              </div>
            ))}
          </div>
        )}
      </PixelFrame>
    </>
  );
}
