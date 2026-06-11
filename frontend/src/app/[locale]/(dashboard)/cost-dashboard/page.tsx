"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ApiError, apiClient } from "@/lib/api-client";
import { useConsoleData } from "@/components/console/use-console-data";
import { PixelButton, PixelFrame, SectionLabel, StatCard } from "@/components/pixel-ui";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
} from "@/components/ui";

interface CostSummary {
  daily_budget_usd: number;
  daily_spent_usd: number;
  budget_used_pct: number;
  total_tokens_today: number;
  total_events_today: number;
}

interface CostEvent {
  id: string;
  created_at: string | null;
  provider: string;
  model: string;
  tokens_used: number;
  cost_usd: number;
}

interface CostEventsResponse {
  items: CostEvent[];
  total: number;
}

function ChartTip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { value: number }[];
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div
      className="pix-mono"
      style={{
        background: "#0e2118",
        border: "3px solid #2e1c0f",
        color: "#d7ffe2",
        padding: "6px 9px",
        fontSize: 14,
      }}
    >
      <div>{label}</div>
      <div>Cost: ${(payload[0]?.value ?? 0).toFixed(6)}</div>
    </div>
  );
}

function progressColor(value: number) {
  if (value > 80) return "#df5b53";
  if (value >= 60) return "#e7b53c";
  return "#6fe08c";
}

export default function CostDashboardPage() {
  const queryClient = useQueryClient();
  const { projects } = useConsoleData();
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [isBudgetDialogOpen, setIsBudgetDialogOpen] = useState(false);
  const [budgetInput, setBudgetInput] = useState("");

  const projectId = selectedProjectId || projects[0]?.id || "";

  const summaryQuery = useQuery<CostSummary, ApiError>({
    queryKey: ["cost-summary", projectId],
    queryFn: () => apiClient.get(`/projects/${projectId}/cost/summary`),
    enabled: !!projectId,
    refetchInterval: 30_000,
  });

  const eventsQuery = useQuery<CostEventsResponse, ApiError>({
    queryKey: ["cost-events", projectId],
    queryFn: () => apiClient.get(`/projects/${projectId}/cost/events`),
    enabled: !!projectId,
    refetchInterval: 30_000,
  });

  const budgetMutation = useMutation({
    mutationFn: (dailyBudgetUsd: number) =>
      apiClient.patch(`/projects/${projectId}/cost/budget`, { daily_budget_usd: dailyBudgetUsd }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["cost-summary", projectId] }),
        queryClient.invalidateQueries({ queryKey: ["cost-events", projectId] }),
      ]);
      setIsBudgetDialogOpen(false);
    },
  });

  const summary = summaryQuery.data;
  const events = eventsQuery.data?.items ?? [];
  const percentUsed = summary?.budget_used_pct ?? 0;

  const chartData = useMemo(
    () =>
      [...events]
        .reverse()
        .map((event) => ({
          label: event.created_at
            ? new Date(event.created_at).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              })
            : "—",
          cost: event.cost_usd,
        })),
    [events],
  );

  const openBudgetDialog = () => {
    setBudgetInput(summary ? String(summary.daily_budget_usd) : "");
    setIsBudgetDialogOpen(true);
  };

  return (
    <>
      <PixelFrame tight>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: 12,
          }}
        >
          <div>
            <div className="pix-eyebrow">Hub Management</div>
            <h2 style={{ margin: 0 }}>Cost &amp; Usage</h2>
          </div>
          {projects.length > 0 && (
            <select
              value={projectId}
              onChange={(event) => setSelectedProjectId(event.target.value)}
              className="pix-mono"
              style={{
                background: "var(--pix-parch2)",
                border: "2px solid var(--pix-frame)",
                padding: "4px 8px",
                fontSize: 14,
              }}
            >
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>
          )}
        </div>
      </PixelFrame>

      {!projectId ? (
        <PixelFrame>
          <div className="pix-empty">No projects yet. Create one first.</div>
        </PixelFrame>
      ) : (
        <>
          <div className="pix-grid-4">
            <StatCard
              label="Daily Budget"
              value={summaryQuery.isLoading ? "…" : `$${(summary?.daily_budget_usd ?? 0).toFixed(2)}`}
              icon="💰"
            />
            <StatCard
              label="Spent Today"
              value={summaryQuery.isLoading ? "…" : `$${(summary?.daily_spent_usd ?? 0).toFixed(4)}`}
              icon="📊"
            />
            <StatCard
              label="Tokens Used"
              value={summaryQuery.isLoading ? "…" : (summary?.total_tokens_today ?? 0).toLocaleString()}
              icon="🔢"
            />
            <StatCard
              label="Budget Used"
              value={summaryQuery.isLoading ? "…" : `${percentUsed.toFixed(1)}%`}
              icon="📈"
            />
          </div>

          <PixelFrame>
            <SectionLabel>Budget Usage</SectionLabel>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 8 }}>
              <div
                style={{
                  flex: 1,
                  height: 16,
                  background: "#1a1a2e",
                  border: "2px solid #4a4238",
                  borderRadius: 2,
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    width: `${Math.max(0, Math.min(percentUsed, 100))}%`,
                    height: "100%",
                    background: progressColor(percentUsed),
                    transition: "width 0.4s",
                  }}
                />
              </div>
              <span className="pix-mono" style={{ minWidth: 54, fontSize: 14 }}>
                {percentUsed.toFixed(1)}%
              </span>
              <PixelButton onClick={openBudgetDialog}>Edit Budget</PixelButton>
            </div>
            {summaryQuery.error && (
              <div className="pix-mono" style={{ marginTop: 10, color: "#df5b53", fontSize: 13 }}>
                {summaryQuery.error.message}
              </div>
            )}
          </PixelFrame>

          <PixelFrame variant="screen">
            <SectionLabel>
              <span style={{ color: "#9bdbaa" }}>Cost per Event · Last 24 Hours</span>
            </SectionLabel>
            {eventsQuery.isLoading ? (
              <div className="pix-empty" style={{ color: "#9bdbaa" }}>
                Loading…
              </div>
            ) : chartData.length === 0 ? (
              <div className="pix-empty" style={{ color: "#9bdbaa" }}>
                No cost events recorded yet.
              </div>
            ) : (
              <div style={{ height: 240 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="2 4" stroke="#1f4a2c" vertical={false} />
                    <XAxis
                      dataKey="label"
                      tick={{
                        fill: "#9bdbaa",
                        fontSize: 11,
                        fontFamily: "VT323, monospace",
                      }}
                      axisLine={{ stroke: "#3f8a59" }}
                      tickLine={false}
                      interval="preserveStartEnd"
                    />
                    <YAxis
                      tick={{
                        fill: "#9bdbaa",
                        fontSize: 11,
                        fontFamily: "VT323, monospace",
                      }}
                      axisLine={false}
                      tickLine={false}
                      tickFormatter={(value: number) => `$${value.toFixed(4)}`}
                    />
                    <Tooltip content={<ChartTip />} />
                    <Line
                      type="monotone"
                      dataKey="cost"
                      stroke="#e7b53c"
                      strokeWidth={2}
                      dot={false}
                      isAnimationActive={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </PixelFrame>

          <PixelFrame>
            <SectionLabel>Recent Cost Events · {eventsQuery.data?.total ?? 0} total</SectionLabel>
            {eventsQuery.isLoading ? (
              <div className="pix-empty">Loading…</div>
            ) : events.length === 0 ? (
              <div className="pix-empty">No events yet.</div>
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
                      <th style={{ textAlign: "left", padding: "4px 8px" }}>Timestamp</th>
                      <th style={{ textAlign: "left", padding: "4px 8px" }}>Provider</th>
                      <th style={{ textAlign: "left", padding: "4px 8px" }}>Model</th>
                      <th style={{ textAlign: "right", padding: "4px 8px" }}>Tokens</th>
                      <th style={{ textAlign: "right", padding: "4px 8px" }}>Cost USD</th>
                    </tr>
                  </thead>
                  <tbody>
                    {events.map((event) => (
                      <tr key={event.id} style={{ borderBottom: "1px solid #4a423840" }}>
                        <td style={{ padding: "4px 8px" }}>
                          {event.created_at ? new Date(event.created_at).toLocaleString() : "—"}
                        </td>
                        <td style={{ padding: "4px 8px" }}>{event.provider}</td>
                        <td style={{ padding: "4px 8px", color: "var(--pix-gold)" }}>
                          {event.model || "—"}
                        </td>
                        <td style={{ padding: "4px 8px", textAlign: "right" }}>
                          {(event.tokens_used ?? 0).toLocaleString()}
                        </td>
                        <td style={{ padding: "4px 8px", textAlign: "right", color: "#e7b53c" }}>
                          ${(event.cost_usd ?? 0).toFixed(6)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </PixelFrame>
        </>
      )}

      <Dialog open={isBudgetDialogOpen} onOpenChange={setIsBudgetDialogOpen}>
        <DialogContent className="pix-root max-w-sm" style={{ background: "var(--pix-parch)", borderColor: "var(--pix-wood-dark)", borderWidth: 3 }}>
          <DialogHeader>
            <DialogTitle style={{ fontFamily: '"Pixelify Sans", sans-serif', fontSize: 18, color: "var(--pix-ink)" }}>Set Daily Budget</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="pix-mono" style={{ fontSize: 13, color: "var(--pix-ink-soft)" }}>
              Update the daily spend limit for this project.
            </div>
            <Input
              type="number"
              min="0"
              step="0.01"
              value={budgetInput}
              onChange={(event) => setBudgetInput(event.target.value)}
              placeholder="25.00"
              style={{ fontFamily: '"VT323", monospace', background: "var(--pix-parch-2)", borderColor: "var(--pix-wood-dark)", color: "var(--pix-ink)" }}
            />
            {budgetMutation.isError && (
              <div className="pix-mono" style={{ color: "#df5b53", fontSize: 13 }}>
                {budgetMutation.error instanceof ApiError
                  ? budgetMutation.error.message
                  : "Failed to update budget"}
              </div>
            )}
          </div>
          <DialogFooter>
            <div className="pix-root flex gap-2">
              <PixelButton onClick={() => setIsBudgetDialogOpen(false)}>Cancel</PixelButton>
              <PixelButton
                variant="green"
                disabled={budgetMutation.isPending || Number(budgetInput) <= 0}
                onClick={() => budgetMutation.mutate(Number(budgetInput))}
              >
                {budgetMutation.isPending ? "Saving…" : "Save Budget"}
              </PixelButton>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
