"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { apiClient } from "@/lib/api-client";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { format, isWithinInterval, startOfDay, startOfMonth, startOfToday, startOfWeek, subDays } from "date-fns";
import { useAuth } from "@/hooks";
import { ROUTES } from "@/lib/constants";
import { useConsoleData, type EnrichedRun, type Project, sortByRecency } from "@/components/console/use-console-data";
import { StatusBadge } from "@/components/run-status/StatusBadge";
import { displayStatusOf, workflowHealthOf } from "@/lib/run-status";
import { useConsolePrefs, type TimeRange } from "@/components/console/use-console-prefs";
import { PixelButton, PixelFrame, PixelSegmented, SectionLabel, StatCard } from "@/components/pixel-ui";

function getGreeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

function rangeStart(range: TimeRange): Date | null {
  switch (range) {
    case "today":
      return startOfToday();
    case "week":
      return startOfWeek(new Date(), { weekStartsOn: 1 });
    case "month":
      return startOfMonth(new Date());
    default:
      return null;
  }
}

function inWindow(run: EnrichedRun, start: Date | null): boolean {
  if (!start) return true;
  const ts = run.started_at ?? run.finished_at;
  if (!ts) return false;
  return new Date(ts) >= start;
}

// ── Pixel-themed recharts tooltip ────────────────────────────────────────────
interface TipPayload {
  name: string;
  value: number;
  color: string;
}
function ChartTip({ active, payload, label }: { active?: boolean; payload?: TipPayload[]; label?: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div
      className="pix-mono"
      style={{
        background: "#0e2118",
        border: "3px solid #2e1c0f",
        color: "#d7ffe2",
        padding: "6px 9px",
        fontSize: 15,
      }}
    >
      <div style={{ marginBottom: 4 }}>{label}</div>
      {payload.map((p) => (
        <div key={p.name} style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ width: 8, height: 8, background: p.color, display: "inline-block" }} />
          <span style={{ textTransform: "capitalize" }}>{p.name}:</span>
          <strong>{p.value}</strong>
        </div>
      ))}
    </div>
  );
}

export default function DashboardPage() {
  const { user } = useAuth();
  const router = useRouter();
  const { prefs } = useConsolePrefs();
  const { projects, agentsMap, workflowsMap, runsMap, allRuns, totalAgents, runsLoading } = useConsoleData();

  const [dashStats, setDashStats] = useState<{
    projects_total: number;
    workflows_running: number;
    workflows_failed: number;
    agents_active: number;
    agents_error: number;
    handoffs_pending: number;
    approvals_waiting: number;
  } | null>(null);

  useEffect(() => {
    apiClient.get("/dashboard/stats").then((data) => setDashStats(data as typeof dashStats)).catch(() => {});
  }, []);


  const firstName = user?.full_name?.split(" ")[0] ?? user?.email?.split("@")[0] ?? "there";

  const start = useMemo(() => rangeStart(prefs.defaultRange), [prefs.defaultRange]);
  const filteredRuns = useMemo(() => allRuns.filter((r) => inWindow(r, start)), [allRuns, start]);

  const totalProjects = projects.length;
  const totalRuns = filteredRuns.length;
  // Workflow Health = share of terminal runs that did NOT error (see workflowHealthOf).
  // complete-reject and limit are intentional outcomes, not failures; active runs are excluded.
  const workflowHealth = useMemo(() => workflowHealthOf(filteredRuns), [filteredRuns]);

  const chartData = useMemo(() => {
    const days = Array.from({ length: 7 }, (_, i) => {
      const d = startOfDay(subDays(new Date(), 6 - i));
      return { date: d, label: format(d, "MMM d"), completed: 0, failed: 0 };
    });
    filteredRuns.forEach((run) => {
      const ts = run.started_at ?? run.finished_at;
      if (!ts) return;
      const runDate = startOfDay(new Date(ts));
      const slot = days.find((d) => isWithinInterval(runDate, { start: d.date, end: d.date }));
      if (!slot) return;
      const ds = displayStatusOf(run);
      if (ds === "error") slot.failed++;
      else if (ds !== "active") slot.completed++;
    });
    return days.map(({ label, completed, failed }) => ({ label, completed, failed }));
  }, [filteredRuns]);

  const chartEmpty = chartData.every((d) => d.completed === 0 && d.failed === 0);

  const lastRunByProject = useMemo(() => {
    const map: Record<string, EnrichedRun> = {};
    projects.forEach((p) => {
      const sorted = sortByRecency((runsMap?.[p.id]?.items ?? []) as EnrichedRun[]);
      if (sorted[0]) map[p.id] = sorted[0];
    });
    return map;
  }, [runsMap, projects]);

  const openProject = (p: Project) => router.push(ROUTES.PROJECT_DETAIL(p.id));


  return (
    <>
      {/* Greeting + range */}
      <PixelFrame tight>
        <div className="pix-greet">
          <div>
            <div className="pix-eyebrow">Overview</div>
            <h2>
              {getGreeting()}, {firstName}
            </h2>
          </div>
          <div className="pix-filters">
            <DashboardRange />
          </div>
        </div>
      </PixelFrame>

      {/* Stat strip */}
      <div className="pix-grid-4">
        <StatCard
          label="Projects"
          value={totalProjects}
          icon="📁"
          sub={`${projects.filter((p) => p.status === "active").length} active`}
          onClick={() => router.push(ROUTES.PROJECTS)}
        />
        <StatCard label="Agents" value={totalAgents} icon="🤖" sub="across all projects" />
        <StatCard
          label="Runs"
          value={totalRuns}
          icon="▶"
          sub={prefs.defaultRange === "all" ? "total" : `this ${prefs.defaultRange === "today" ? "day" : prefs.defaultRange}`}
        />
        <StatCard
          label="Workflow Health"
          value={workflowHealth.terminal === 0 ? "—" : `${workflowHealth.pct}%`}
          icon="📈"
          trend={workflowHealth.terminal === 0 ? undefined : workflowHealth.pct >= 50 ? "up" : "down"}
          sub={workflowHealth.terminal === 0 ? "no finished runs yet" : `${workflowHealth.healthy}/${workflowHealth.terminal} non-error`}
        />
      </div>

      {/* Control Center stats */}
      <div className="pix-grid-4">
        <StatCard
          label="Handoffs"
          value={dashStats?.handoffs_pending ?? 0}
          icon="🔄"
          sub="pending"
          onClick={() => router.push(ROUTES.HANDOFFS)}
        />
        <StatCard
          label="Approvals"
          value={dashStats?.approvals_waiting ?? 0}
          icon="⏸"
          sub="waiting"
        />
        <StatCard
          label="Running"
          value={dashStats?.workflows_running ?? 0}
          icon="🏃"
          sub="workflows"
        />
        <StatCard
          label="Failed"
          value={dashStats?.workflows_failed ?? 0}
          icon="💥"
          sub="workflows"
        />
      </div>

      {/* Runs over time chart */}
      <PixelFrame variant="screen">
        <SectionLabel>
          <span style={{ color: "#9bdbaa" }}>Runs Over Time · last 7 days</span>
        </SectionLabel>
        {runsLoading ? (
          <div className="pix-empty" style={{ color: "#9bdbaa" }}>
            Loading run data…
          </div>
        ) : chartEmpty ? (
          <div className="pix-empty" style={{ color: "#9bdbaa" }}>
            No run data in this window yet.
          </div>
        ) : (
          <div style={{ height: 200 }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 6, right: 6, left: -18, bottom: 0 }}>
                <defs>
                  <linearGradient id="pixGradDone" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#6fe08c" stopOpacity={0.4} />
                    <stop offset="100%" stopColor="#6fe08c" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="pixGradFail" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#df5b53" stopOpacity={0.4} />
                    <stop offset="100%" stopColor="#df5b53" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="2 4" stroke="#1f4a2c" vertical={false} />
                <XAxis
                  dataKey="label"
                  tick={{ fill: "#9bdbaa", fontSize: 12, fontFamily: "VT323, monospace" }}
                  axisLine={{ stroke: "#3f8a59" }}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fill: "#9bdbaa", fontSize: 12, fontFamily: "VT323, monospace" }}
                  axisLine={false}
                  tickLine={false}
                  allowDecimals={false}
                />
                <Tooltip content={<ChartTip />} />
                <Area
                  type="monotone"
                  dataKey="completed"
                  stroke="#6fe08c"
                  strokeWidth={2}
                  fill="url(#pixGradDone)"
                  isAnimationActive={false}
                />
                <Area
                  type="monotone"
                  dataKey="failed"
                  stroke="#e7b53c"
                  strokeWidth={2}
                  fill="url(#pixGradFail)"
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </PixelFrame>

      {/* Project cards */}
      <PixelFrame>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
          <div className="pix-label" style={{ marginBottom: 0 }}>Projects · {totalProjects}</div>
          <PixelButton variant="gold" onClick={() => router.push("/projects/new")}>
            + New Project
          </PixelButton>
        </div>
        {projects.length === 0 ? (
          <div className="pix-empty">
            No projects yet.
            <div style={{ marginTop: 12 }}>
              <PixelButton variant="gold" onClick={() => router.push("/projects/new")}>
                + Create Project
              </PixelButton>
            </div>
          </div>
        ) : (
          <div className="pix-grid-cards">
            {projects.map((p) => {
              const agentCount = agentsMap?.[p.id]?.total ?? 0;
              const workflowCount = workflowsMap?.[p.id]?.total ?? 0;
              const runCount = runsMap?.[p.id]?.items.length ?? 0;
              const lastRun = lastRunByProject[p.id];
              return (
                <PixelFrame key={p.id} variant="parchment" tight className="pix-pcard" onClick={() => openProject(p)}>
                  <div className="pix-pcard-head">
                    <span className="pix-pname">🏠 {p.name}</span>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      {p.status === "active" ? (
                        <span className="pix-pill pix-completed">active</span>
                      ) : (
                        <span className="pix-pill">{p.status}</span>
                      )}
                      <button
                        type="button"
                        title="Edit project"
                        onClick={(e) => { e.stopPropagation(); router.push(ROUTES.PROJECTS + "?edit=" + p.id); }}
                        style={{ background: "none", border: "none", cursor: "pointer", padding: "0 2px", fontSize: 14, lineHeight: 1, color: "var(--pix-ink)", opacity: 0.6 }}
                        onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.opacity = "1"; }}
                        onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.opacity = "0.6"; }}
                      >
                        ✏️
                      </button>
                    </div>
                  </div>
                  <div className="pix-pcard-metrics">
                    <span>🤖 {agentsMap ? agentCount : "—"}</span>
                    <span>🧩 {workflowsMap ? workflowCount : "—"}</span>
                    <span>▶ {runsMap ? runCount : "—"}</span>
                  </div>
                  <div className="pix-mono" style={{ fontSize: 14 }}>
                    {lastRun ? (
                      <StatusBadge run={lastRun} />
                    ) : (
                      <span className="pix-muted">no runs yet</span>
                    )}
                  </div>
                  <div className="pix-pcard-actions">
                    <PixelButton
                      onClick={(e) => {
                        e.stopPropagation();
                        router.push(`/projects/${p.id}/room`);
                      }}
                    >
                      🚪 Room
                    </PixelButton>
                    <PixelButton
                      onClick={(e) => {
                        e.stopPropagation();
                        router.push(ROUTES.PROJECT_DETAIL(p.id) + "?tab=workflows");
                      }}
                    >
                      🧩 Workflows
                    </PixelButton>
                    <PixelButton
                      variant="green"
                      onClick={(e) => {
                        e.stopPropagation();
                        router.push(ROUTES.PROJECT_DETAIL(p.id) + "?tab=agents");
                      }}
                    >
                      + Agent
                    </PixelButton>
                  </div>
                </PixelFrame>
              );
            })}
          </div>
        )}
      </PixelFrame>

    </>
  );
}

/** Range segmented control that writes through to persisted prefs. */
function DashboardRange() {
  const { prefs, update } = useConsolePrefs();
  const rangeOptions: { value: TimeRange; label: string }[] = [
    { value: "today", label: "Today" },
    { value: "week", label: "Week" },
    { value: "month", label: "Month" },
    { value: "all", label: "All" },
  ];
  return (
    <PixelSegmented<TimeRange>
      options={rangeOptions}
      value={prefs.defaultRange}
      onChange={(v) => update("defaultRange", v)}
    />
  );
}
