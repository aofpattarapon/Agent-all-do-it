"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";

// ── API shapes ───────────────────────────────────────────────────────────────

export interface Project {
  id: string;
  name: string;
  description: string | null;
  status: string;
  created_at: string;
}
interface ProjectList {
  items: Project[];
  total: number;
}
export interface AgentItem {
  id: string;
  name?: string;
  is_active?: boolean;
}
interface AgentList {
  items: AgentItem[];
  total: number;
}
interface WorkflowList {
  items: { id: string; name: string; is_enabled?: boolean }[];
  total: number;
}
export interface RunItem {
  id: string;
  status: string;
  trigger: string;
  started_at: string | null;
  finished_at: string | null;
  output_text: string;
  error_text?: string;
  workflow_name?: string;
  agent_name?: string;
}
interface RunList {
  items: RunItem[];
  total: number;
}

export interface EnrichedRun extends RunItem {
  projectId: string;
  projectName: string;
}

export interface TeamMember {
  id: string;
  name: string;
  projectName: string;
  status: "idle" | "running" | "done" | "error";
}

/** Cap-concurrency parallel fetch. */
async function mapWithConcurrency<I, O>(items: I[], limit: number, fn: (item: I) => Promise<O>): Promise<O[]> {
  const out: O[] = new Array(items.length);
  let cursor = 0;
  const workers = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (cursor < items.length) {
      const idx = cursor++;
      out[idx] = await fn(items[idx] as I);
    }
  });
  await Promise.all(workers);
  return out;
}

function sortByRecency<T extends { started_at: string | null; finished_at: string | null }>(items: T[]): T[] {
  return [...items].sort((a, b) => {
    const ta = a.started_at ?? a.finished_at ?? "";
    const tb = b.started_at ?? b.finished_at ?? "";
    return tb.localeCompare(ta);
  });
}

/**
 * Shared loader for the pixel console (dashboard / history / settings sidebar).
 * Lists projects, then fetches agents/workflows/runs per project with capped concurrency.
 */
export function useConsoleData() {
  const projectsQuery = useQuery<ProjectList>({
    queryKey: ["projects"],
    queryFn: () => apiClient.get<ProjectList>("/projects"),
  });

  const projects = useMemo(() => projectsQuery.data?.items ?? [], [projectsQuery.data]);
  const projectIds = projects.map((p) => p.id).join(",");

  const agentsQuery = useQuery<Record<string, AgentList>>({
    queryKey: ["console-agents", projectIds],
    enabled: projects.length > 0,
    queryFn: async () => {
      const results = await mapWithConcurrency(projects, 4, (p) =>
        apiClient
          .get<AgentList>(`/projects/${p.id}/agents`)
          .then((d) => [p.id, d] as const)
          .catch(() => [p.id, { items: [], total: 0 }] as const),
      );
      return Object.fromEntries(results);
    },
  });

  const workflowsQuery = useQuery<Record<string, WorkflowList>>({
    queryKey: ["console-workflows", projectIds],
    enabled: projects.length > 0,
    queryFn: async () => {
      const results = await mapWithConcurrency(projects, 4, (p) =>
        apiClient
          .get<WorkflowList>(`/projects/${p.id}/workflows`)
          .then((d) => [p.id, d] as const)
          .catch(() => [p.id, { items: [], total: 0 }] as const),
      );
      return Object.fromEntries(results);
    },
  });

  const runsQuery = useQuery<Record<string, RunList>>({
    queryKey: ["console-runs", projectIds],
    enabled: projects.length > 0,
    queryFn: async () => {
      const results = await mapWithConcurrency(projects, 4, (p) =>
        apiClient
          .get<RunList>(`/projects/${p.id}/runs`)
          .then((d) => [p.id, d] as const)
          .catch(() => [p.id, { items: [], total: 0 }] as const),
      );
      return Object.fromEntries(results);
    },
  });

  const agentsMap = agentsQuery.data;
  const workflowsMap = workflowsQuery.data;
  const runsMap = runsQuery.data;

  const allRuns = useMemo<EnrichedRun[]>(() => {
    if (!runsMap) return [];
    return projects.flatMap((p) =>
      (runsMap[p.id]?.items ?? []).map((r) => ({ ...r, projectId: p.id, projectName: p.name })),
    );
  }, [runsMap, projects]);

  // Derive a status for each agent best-effort from the project's most recent run.
  const team = useMemo<TeamMember[]>(() => {
    if (!agentsMap) return [];
    const members: TeamMember[] = [];
    projects.forEach((p) => {
      const lastRun = sortByRecency(runsMap?.[p.id]?.items ?? [])[0];
      let status: TeamMember["status"] = "idle";
      if (lastRun) {
        if (lastRun.status === "running") status = "running";
        else if (lastRun.status === "completed") status = "done";
        else if (lastRun.status === "failed") status = "error";
      }
      (agentsMap[p.id]?.items ?? []).forEach((a, i) => {
        members.push({
          id: a.id,
          name: a.name ?? `Agent ${i + 1}`,
          projectName: p.name,
          status,
        });
      });
    });
    return members;
  }, [agentsMap, runsMap, projects]);

  const totalProjects = projects.length;
  const totalAgents = useMemo(
    () => (agentsMap ? projects.reduce((acc, p) => acc + (agentsMap[p.id]?.total ?? 0), 0) : 0),
    [agentsMap, projects],
  );
  const totalRuns = allRuns.length;
  const successRate = useMemo(() => {
    if (totalRuns === 0) return 0;
    const done = allRuns.filter((r) => r.status === "completed").length;
    return Math.round((done / totalRuns) * 100);
  }, [allRuns, totalRuns]);

  const isLoading =
    projectsQuery.isLoading || agentsQuery.isLoading || workflowsQuery.isLoading || runsQuery.isLoading;

  return {
    projects,
    agentsMap,
    workflowsMap,
    runsMap,
    allRuns,
    team,
    totalProjects,
    totalAgents,
    totalRuns,
    successRate,
    isLoading,
    runsLoading: runsQuery.isLoading,
  };
}

export { sortByRecency };
