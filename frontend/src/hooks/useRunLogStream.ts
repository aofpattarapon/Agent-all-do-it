"use client";

import { useEffect, useRef, useState } from "react";

export interface RunLogStep {
  step_index: number;
  agent_name: string;
  status: string;
  output_json: Record<string, unknown>;
  started_at: string | null;
  ended_at: string | null;
}

interface UseRunLogStreamOptions {
  projectId: string;
  runId: string;
  /** Initial run status — if already terminal, stream is skipped */
  initialStatus?: string;
}

interface UseRunLogStreamResult {
  steps: RunLogStep[];
  runStatus: string;
  elapsedSeconds: number | null;
  connected: boolean;
  error: string | null;
}

const TERMINAL = new Set(["completed", "failed", "cancelled", "waiting_approval"]);
const MAX_RETRIES = 3;

export function useRunLogStream({
  projectId,
  runId,
  initialStatus = "",
}: UseRunLogStreamOptions): UseRunLogStreamResult {
  const [steps, setSteps] = useState<RunLogStep[]>([]);
  const [runStatus, setRunStatus] = useState(initialStatus);
  const [elapsedSeconds, setElapsedSeconds] = useState<number | null>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const retryCount = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const seenIndices = useRef<Set<number>>(new Set());

  useEffect(() => {
    if (TERMINAL.has(initialStatus)) return;

    let stopped = false;

    async function connect() {
      if (stopped) return;

      abortRef.current = new AbortController();
      const { signal } = abortRef.current;

      try {
        const res = await fetch(
          `/api/projects/${projectId}/runs/${runId}/stream`,
          { signal, headers: { Accept: "text/event-stream" } },
        );

        if (!res.ok || !res.body) {
          const text = await res.text().catch(() => "");
          setError(`Stream error ${res.status}: ${text}`);
          return;
        }

        setConnected(true);
        setError(null);

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done || stopped) break;

          buffer += decoder.decode(value, { stream: true });
          const blocks = buffer.split("\n\n");
          buffer = blocks.pop() ?? "";

          for (const block of blocks) {
            let eventType = "message";
            let data = "";

            for (const line of block.split("\n")) {
              if (line.startsWith("event: ")) eventType = line.slice(7).trim();
              else if (line.startsWith("data: ")) data = line.slice(6).trim();
            }

            if (!data) continue;

            try {
              const parsed = JSON.parse(data) as Record<string, unknown>;

              if (eventType === "step") {
                const step = parsed as unknown as RunLogStep;
                if (!seenIndices.current.has(step.step_index)) {
                  seenIndices.current.add(step.step_index);
                  setSteps((prev) => {
                    const next = [...prev, step];
                    next.sort((a, b) => a.step_index - b.step_index);
                    return next;
                  });
                }
              } else if (eventType === "run_status") {
                const status = (parsed.status as string) ?? "";
                const elapsed = (parsed.elapsed_seconds as number | null) ?? null;
                setRunStatus(status);
                setElapsedSeconds(elapsed);
                if (TERMINAL.has(status)) {
                  stopped = true;
                  setConnected(false);
                  break;
                }
              }
            } catch {
              // ignore malformed SSE data
            }
          }

          if (stopped) break;
        }

        setConnected(false);
      } catch (err: unknown) {
        if (stopped) return;
        setConnected(false);
        const msg = err instanceof Error ? err.message : String(err);
        if (msg.includes("aborted")) return;

        setError(msg);
        if (retryCount.current < MAX_RETRIES) {
          retryCount.current += 1;
          setTimeout(connect, 2000);
        }
      }
    }

    connect();

    return () => {
      stopped = true;
      abortRef.current?.abort();
      setConnected(false);
    };
  }, [projectId, runId, initialStatus]);

  return { steps, runStatus, elapsedSeconds, connected, error };
}
