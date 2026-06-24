"use client";

import { useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { LayoutDashboard, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { apiClient } from "@/lib/api-client";
import { PixelFrame, SectionLabel, PixelButton } from "@/components/pixel-ui";
import type { Project, RunItem } from "@/components/console/use-console-data";
import { displayStatusOf, isErrorRun } from "@/lib/run-status";
import { KanbanColumn } from "./KanbanColumn";

interface EnrichedRun extends RunItem {
  projectId: string;
  projectName: string;
}

interface RunList {
  items: RunItem[];
  total: number;
}

interface ProjectList {
  items: Project[];
  total: number;
}

// Columns are driven by the canonical display_status taxonomy. "Done" is any terminal,
// non-error outcome (complete-trade / complete-reject / limit); "Error" uses the canonical
// isErrorRun predicate so handoff failures count as errors while HAWK no-majority does not.
const COLUMNS: { label: string; color: "gray" | "blue" | "yellow" | "red" | "green"; matcher: (r: EnrichedRun) => boolean }[] = [
  { label: "Active", color: "blue", matcher: (r) => displayStatusOf(r) === "active" },
  { label: "Done", color: "green", matcher: (r) => displayStatusOf(r) !== "active" && !isErrorRun(r) },
  { label: "Error", color: "red", matcher: (r) => isErrorRun(r) },
];

interface WorkboardPageProps {
  projectId?: string;
}

export function WorkboardPage({ projectId: propProjectId }: WorkboardPageProps) {
  const { locale: _locale } = useParams<{ locale: string }>();
  const queryClient = useQueryClient();
  const [selectedProject, setSelectedProject] = useState<string>("all");
  const [dateFrom, setDateFrom] = useState<string>("");
  const [dateTo, setDateTo] = useState<string>("");

  const isEmbedded = !!propProjectId;

  // Fetch all projects (only needed for global view)
  const projectsQuery = useQuery<ProjectList>({
    queryKey: ["projects"],
    queryFn: () => apiClient.get<ProjectList>("/projects"),
    enabled: !isEmbedded,
  });

  const projects = useMemo(() => {
    if (isEmbedded) {
      return propProjectId ? [{ id: propProjectId, name: "", description: null, status: "", created_at: "" }] : [];
    }
    return projectsQuery.data?.items ?? [];
  }, [projectsQuery.data, isEmbedded, propProjectId]);

  const projectIds = isEmbedded && propProjectId ? propProjectId : projects.map((p) => p.id).join(",");

  // Fetch runs with polling
  const runsQuery = useQuery<Record<string, RunList>>({
    queryKey: ["workboard-runs", projectIds],
    enabled: isEmbedded ? !!propProjectId : projects.length > 0,
    queryFn: async () => {
      const targets = isEmbedded && propProjectId ? [propProjectId] : projects.map((p) => p.id);
      const results = await Promise.all(
        targets.map((pid) =>
          apiClient
            .get<RunList>(`/projects/${pid}/runs?limit=100`)
            .then((d) => [pid, d] as const)
            .catch(() => [pid, { items: [], total: 0 }] as const),
        ),
      );
      return Object.fromEntries(results);
    },
    refetchInterval: 5000,
  });

  // Merge all runs into flat enriched array
  const allRuns = useMemo<EnrichedRun[]>(() => {
    if (!runsQuery.data) return [];
    const targets = isEmbedded && propProjectId ? [propProjectId] : projects.map((p) => p.id);
    return targets.flatMap((pid) => {
      const projectName = projects.find((p) => p.id === pid)?.name ?? "";
      return (runsQuery.data[pid]?.items ?? []).map((run) => ({
        ...run,
        projectId: pid,
        projectName,
      }));
    });
  }, [runsQuery.data, projects, isEmbedded, propProjectId]);

  // Filter by selected project and date range
  const filteredRuns = useMemo(() => {
    let runs = allRuns;
    if (!isEmbedded && selectedProject !== "all") {
      runs = runs.filter((r) => r.projectId === selectedProject);
    }
    if (dateFrom) {
      const from = new Date(dateFrom).getTime();
      runs = runs.filter((r) => {
        const ts = r.started_at ?? r.finished_at;
        return ts ? new Date(ts).getTime() >= from : true;
      });
    }
    if (dateTo) {
      const to = new Date(dateTo).getTime() + 86400000; // include full end day
      runs = runs.filter((r) => {
        const ts = r.started_at ?? r.finished_at;
        return ts ? new Date(ts).getTime() < to : true;
      });
    }
    return runs;
  }, [allRuns, selectedProject, isEmbedded, dateFrom, dateTo]);

  // Group by column
  const grouped = useMemo(() => {
    const map: Record<string, EnrichedRun[]> = {};
    COLUMNS.forEach((col) => {
      map[col.label] = filteredRuns.filter((r) => col.matcher(r));
    });
    return map;
  }, [filteredRuns]);

  // Active runs count (not done/error)
  const activeCount = useMemo(
    () => filteredRuns.filter((r) => displayStatusOf(r) === "active").length,
    [filteredRuns],
  );

  const queuedRuns = useMemo(
    () => filteredRuns.filter((r) => r.status === "queued"),
    [filteredRuns],
  );

  const clearableRuns = useMemo(
    () => filteredRuns.filter((r) => r.status !== "running"),
    [filteredRuns],
  );

  // Mutations
  const approveMutation = useMutation({
    mutationFn: ({ projectId, runId }: { projectId: string; runId: string }) =>
      apiClient.post(`/projects/${projectId}/runs/${runId}/approve`),
    onSuccess: () => invalidateRuns(),
  });

  const rejectMutation = useMutation({
    mutationFn: ({ projectId, runId }: { projectId: string; runId: string }) =>
      apiClient.post(`/projects/${projectId}/runs/${runId}/reject`),
    onSuccess: () => invalidateRuns(),
  });

  const retryMutation = useMutation({
    mutationFn: ({ projectId, runId }: { projectId: string; runId: string }) =>
      apiClient.post(`/projects/${projectId}/runs/${runId}/retry`),
    onSuccess: () => invalidateRuns(),
  });

  const cancelMutation = useMutation({
    mutationFn: ({ projectId, runId }: { projectId: string; runId: string }) =>
      apiClient.patch(`/projects/${projectId}/runs/${runId}`, { status: "cancelled" }),
    onSuccess: () => invalidateRuns(),
  });

  const overrideApproveMutation = useMutation({
    mutationFn: ({ projectId, runId }: { projectId: string; runId: string }) =>
      apiClient.post(`/projects/${projectId}/runs/${runId}/override-approve`),
    onSuccess: () => invalidateRuns(),
  });

  function invalidateRuns() {
    queryClient.invalidateQueries({ queryKey: ["workboard-runs"] });
    queryClient.invalidateQueries({ queryKey: ["console-runs"] });
    queryClient.invalidateQueries({ queryKey: ["runs"] });
  }

  function handleAction(action: "approve" | "reject" | "retry" | "cancel" | "override-approve", runId: string, projectId: string) {
    const payload = { projectId, runId };
    if (action === "approve") approveMutation.mutate(payload);
    if (action === "reject") rejectMutation.mutate(payload);
    if (action === "retry") retryMutation.mutate(payload);
    if (action === "cancel") cancelMutation.mutate(payload);
    if (action === "override-approve") overrideApproveMutation.mutate(payload);
  }

  async function handleCleanAllQueued() {
    if (queuedRuns.length === 0) {
      toast.info("No queued runs to clean");
      return;
    }
    if (!confirm(`Cancel all ${queuedRuns.length} queued runs?`)) return;

    let cancelled = 0;
    let failed = 0;
    await Promise.all(
      queuedRuns.map(async (run) => {
        try {
          await apiClient.patch(`/projects/${run.projectId}/runs/${run.id}`, { status: "cancelled" });
          cancelled++;
        } catch {
          failed++;
        }
      }),
    );
    invalidateRuns();
    if (cancelled > 0) toast.success(`Cancelled ${cancelled} queued runs`);
    if (failed > 0) toast.error(`Failed to cancel ${failed} runs`);
  }

  async function handleCleanAll() {
    if (clearableRuns.length === 0) {
      toast.info("Nothing to clean");
      return;
    }
    if (!confirm(`Clear all ${clearableRuns.length} runs? (running runs are skipped)`)) return;

    const ACTIVE = ["queued", "waiting_approval", "paused"];
    let done = 0;
    let errors = 0;
    await Promise.all(
      clearableRuns.map(async (run) => {
        try {
          if (ACTIVE.includes(run.status)) {
            await apiClient.patch(`/projects/${run.projectId}/runs/${run.id}`, { status: "cancelled" });
          }
          await apiClient.delete(`/projects/${run.projectId}/runs/${run.id}`);
          done++;
        } catch {
          errors++;
        }
      }),
    );
    invalidateRuns();
    if (done > 0) toast.success(`Cleared ${done} runs`);
    if (errors > 0) toast.error(`Failed to clear ${errors} runs`);
  }

  const isLoading = (!isEmbedded && projectsQuery.isLoading) || runsQuery.isLoading;

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <PixelFrame tight className="mb-4">
        <div className="flex flex-wrap items-center justify-between gap-4 px-4 py-3">
          <div className="flex items-center gap-3">
            <LayoutDashboard size={20} style={{ color: "var(--pix-gold)" }} />
            <h1 style={{ fontFamily: '"VT323", monospace', fontSize: 24, margin: 0 }}>Workboard</h1>
            <span
              className="rounded px-2 py-0.5 text-sm"
              style={{ fontFamily: '"VT323", monospace', background: "var(--pix-wood-dark)", color: "var(--pix-parch)" }}
            >
              {activeCount} active
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {/* Date range filter */}
            <SectionLabel>From</SectionLabel>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="rounded border px-2 py-1 text-sm"
              style={{
                fontFamily: '"VT323", monospace',
                background: "var(--pix-parch)",
                borderColor: "var(--pix-border)",
                color: "var(--pix-ink)",
              }}
            />
            <SectionLabel>To</SectionLabel>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="rounded border px-2 py-1 text-sm"
              style={{
                fontFamily: '"VT323", monospace',
                background: "var(--pix-parch)",
                borderColor: "var(--pix-border)",
                color: "var(--pix-ink)",
              }}
            />
            {(dateFrom || dateTo) && (
              <PixelButton
                onClick={() => { setDateFrom(""); setDateTo(""); }}
                className="text-xs"
              >
                ✕ Clear
              </PixelButton>
            )}

            {queuedRuns.length > 0 && (
              <PixelButton variant="red" onClick={handleCleanAllQueued} className="text-xs">
                <Trash2 size={12} /> Clean All Queued ({queuedRuns.length})
              </PixelButton>
            )}
            {clearableRuns.length > 0 && (
              <PixelButton variant="red" onClick={handleCleanAll} className="text-xs">
                <Trash2 size={12} /> Clean All ({clearableRuns.length})
              </PixelButton>
            )}

            {!isEmbedded && (
              <>
                <SectionLabel>Project</SectionLabel>
                <select
                  value={selectedProject}
                  onChange={(e) => setSelectedProject(e.target.value)}
                  className="rounded border px-2 py-1 text-sm"
                  style={{
                    fontFamily: '"VT323", monospace',
                    background: "var(--pix-parch)",
                    borderColor: "var(--pix-border)",
                    color: "var(--pix-ink)",
                  }}
                >
                  <option value="all">All Projects</option>
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </>
            )}
          </div>
        </div>
      </PixelFrame>

      {/* Loading */}
      {isLoading && (
        <div className="py-12 text-center" style={{ fontFamily: '"VT323", monospace' }}>
          Loading runs…
        </div>
      )}

      {/* Kanban Board */}
      {!isLoading && (
        <div className="flex flex-1 gap-4 overflow-x-auto pb-4" data-testid="kanban-board">
          {COLUMNS.map((col) => (
            <KanbanColumn
              key={col.label}
              label={col.label}
              color={col.color}
              runs={grouped[col.label] ?? []}
              onAction={handleAction}
            />
          ))}
        </div>
      )}
    </div>
  );
}
