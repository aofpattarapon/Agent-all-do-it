"use client";

// Agents Quality read-only dashboard (Phase F).
//
// Aggregates run_steps, runs, handoffs, and agent_votes into per-agent quality
// metrics. No prompt changes, no model/runtime changes, no trading decisions.

import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  ClipboardX,
  RefreshCcw,
  ShieldAlert,
  Sparkles,
  XCircle,
} from "lucide-react";
import type { ReactNode } from "react";

import { PixelFrame, SectionLabel } from "@/components/pixel-ui";
import { apiClient } from "@/lib/api-client";

export interface AgentQuality {
  agent_id: string;
  name: string;
  role: string;
  is_active: boolean;
  total_steps: number;
  total_runs: number;
  successful_outputs: number;
  failed_outputs: number;
  validation_failures: number;
  contract_failures: number;
  retry_count: number;
  error_runs: number;
  last_activity: string | null;
  quality_rate: number;
}

export interface AgentQualityList {
  items: AgentQuality[];
  generated_at: string;
}

interface UseAgentQualityResult {
  data: AgentQualityList | undefined;
  isLoading: boolean;
  isError: boolean;
}

export function useAgentQuality(projectId: string): UseAgentQualityResult {
  return useQuery<AgentQualityList>({
    queryKey: ["agents-quality", projectId],
    queryFn: () => apiClient.get<AgentQualityList>(`/projects/${projectId}/agents/quality`),
  });
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function QualityPill({
  label,
  tone,
  testId,
}: {
  label: string;
  tone: string;
  testId?: string;
}) {
  return (
    <span
      className="pix-pill"
      style={{ color: tone, borderColor: tone }}
      data-testid={testId}
    >
      {label}
    </span>
  );
}

/** Quality-rate pill with tone derived from the rate (>=80 green, >=50 orange, else red). */
export function QualityRatePill({ rate, testId }: { rate: number; testId?: string }) {
  const successTone = "var(--pix-success, #4ade80)";
  const dangerTone = "var(--pix-danger, #f87171)";
  const warnTone = "#f97316";
  const tone = rate >= 80 ? successTone : rate >= 50 ? warnTone : dangerTone;
  return <QualityPill label={`${rate}% quality`} tone={tone} testId={testId} />;
}

function MetricRow({
  label,
  value,
  icon,
  tone,
  testId,
}: {
  label: string;
  value: ReactNode;
  icon?: ReactNode;
  tone?: string;
  testId?: string;
}) {
  return (
    <div
      className="flex items-center justify-between gap-3 py-1"
      style={{ fontFamily: '"VT323", monospace' }}
      data-testid={testId}
    >
      <span className="flex items-center gap-1.5 pix-row-sub" style={{ opacity: 0.7 }}>
        {icon}
        {label}
      </span>
      <span style={{ color: tone }}>{value}</span>
    </div>
  );
}

/** Per-agent metrics grid + last-activity line (no identity header / frame). Reused
 *  standalone in the Quality card and merged into the Agents roster card. */
export function AgentQualityMetrics({ agent }: { agent: AgentQuality }) {
  const successTone = "var(--pix-success, #4ade80)";
  const dangerTone = "var(--pix-danger, #f87171)";

  return (
    <>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <MetricRow
            label="Total steps"
            value={agent.total_steps}
            testId="agent-total-steps"
          />
          <MetricRow
            label="Total runs"
            value={agent.total_runs}
            testId="agent-total-runs"
          />
          <MetricRow
            label="Successful outputs"
            value={agent.successful_outputs}
            icon={<CheckCircle2 className="h-3.5 w-3.5" />}
            tone={successTone}
            testId="agent-successful-outputs"
          />
          <MetricRow
            label="Failed outputs"
            value={agent.failed_outputs}
            icon={<XCircle className="h-3.5 w-3.5" />}
            tone={agent.failed_outputs > 0 ? dangerTone : undefined}
            testId="agent-failed-outputs"
          />
          <MetricRow
            label="Validation failures"
            value={agent.validation_failures}
            icon={<ShieldAlert className="h-3.5 w-3.5" />}
            tone={agent.validation_failures > 0 ? dangerTone : undefined}
            testId="agent-validation-failures"
          />
          <MetricRow
            label="Contract failures"
            value={agent.contract_failures}
            icon={<ClipboardX className="h-3.5 w-3.5" />}
            tone={agent.contract_failures > 0 ? dangerTone : undefined}
            testId="agent-contract-failures"
          />
          <MetricRow
            label="Retries"
            value={agent.retry_count}
            icon={<RefreshCcw className="h-3.5 w-3.5" />}
            testId="agent-retry-count"
          />
          <MetricRow
            label="Error runs"
            value={agent.error_runs}
            icon={<AlertTriangle className="h-3.5 w-3.5" />}
            tone={agent.error_runs > 0 ? dangerTone : undefined}
            testId="agent-error-runs"
          />
        </div>

        <div
          className="pt-1 text-xs opacity-70"
          style={{ fontFamily: '"VT323", monospace' }}
          data-testid="agent-last-activity"
        >
          Last activity: {formatDate(agent.last_activity)}
        </div>
    </>
  );
}

function AgentQualityCard({ agent }: { agent: AgentQuality }) {
  return (
    <PixelFrame tight data-testid="agent-quality-card">
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <Bot className="h-4 w-4" style={{ color: "var(--pix-gold)" }} />
          <span className="pix-row-title" data-testid="agent-name">{agent.name}</span>
          <span className="pix-pill pix-gold" data-testid="agent-role">
            {agent.role}
          </span>
          {!agent.is_active && <span className="pix-pill">inactive</span>}
          <QualityRatePill rate={agent.quality_rate} testId="agent-quality-rate" />
        </div>
        <AgentQualityMetrics agent={agent} />
      </div>
    </PixelFrame>
  );
}

/** Read-only explainer note shown above the Agents roster. */
export function AgentsQualityNote() {
  return (
    <PixelFrame tight>
      <div
        className="flex items-start gap-2"
        style={{ fontFamily: '"VT323", monospace', fontSize: 13, opacity: 0.85 }}
        data-testid="agents-quality-read-only-note"
      >
        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
        <span>
          HAWK no-majority, SAGE veto, complete-reject, and limit pauses are
          intentional workflow outcomes, not agent failures. Handoff validation /
          contract failures and schema/SL/TP validation errors are counted as
          agent-output quality failures.
        </span>
      </div>
    </PixelFrame>
  );
}

export function AgentsQualityView({ projectId }: { projectId: string }) {
  const { data, isLoading, isError } = useAgentQuality(projectId);
  const agents = data?.items ?? [];
  const failed = isError;

  return (
    <div className="space-y-4" data-testid="agents-quality-view">
      <PixelFrame tight>
        <div
          className="flex flex-wrap items-center gap-2"
          style={{ fontFamily: '"VT323", monospace', fontSize: 18 }}
        >
          <Sparkles className="h-4 w-4" />
          <span>Agent Quality</span>
          <span className="ml-1 text-xs opacity-60">— read-only metrics</span>
        </div>
      </PixelFrame>

      <AgentsQualityNote />

      {isLoading ? (
        <PixelFrame>
          <div className="pix-empty" style={{ fontFamily: '"VT323", monospace' }}>
            Loading agent quality metrics…
          </div>
        </PixelFrame>
      ) : failed ? (
        <PixelFrame>
          <div
            className="pix-empty"
            style={{ fontFamily: '"VT323", monospace', color: "var(--pix-danger)" }}
            data-testid="agents-quality-unavailable"
          >
            Agent quality metrics are currently unavailable. The agent roster below remains functional.
          </div>
        </PixelFrame>
      ) : agents.length === 0 ? (
        <PixelFrame>
          <div className="pix-empty" data-testid="agents-quality-empty">
            <Bot className="mx-auto mb-2 h-8 w-8" />
            No agent quality data yet. Metrics appear once agents participate in runs.
          </div>
        </PixelFrame>
      ) : (
        <div className="space-y-2">
          <SectionLabel>Per-Agent Metrics ({agents.length})</SectionLabel>
          {agents.map((agent) => (
            <AgentQualityCard key={agent.agent_id} agent={agent} />
          ))}
        </div>
      )}
    </div>
  );
}
