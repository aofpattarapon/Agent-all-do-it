"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertCircle,
  CheckCircle2,
  Cpu,
  Database,
  HardDrive,
  RefreshCw,
  Server,
  Wifi,
  Zap,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { PixelFrame, PixelButton, SectionLabel } from "@/components/pixel-ui";
import { apiClient } from "@/lib/api-client";

type ServiceStatus = "operational" | "degraded" | "outage" | "unknown";

interface ServiceHealth {
  key: string;
  name: string;
  description: string;
  icon: LucideIcon;
  status: ServiceStatus;
  uptime90d: number;
  latencyMs?: number;
  detail?: string;
}

interface BackendHealthResp {
  status?: string;
  database?: { status?: string; latency_ms?: number };
  redis?: { status?: string; latency_ms?: number };
  vector_store?: { status?: string; latency_ms?: number };
  stripe?: { status?: string };
  llm?: { status?: string; provider?: string };
  worker?: { status?: string };
}

const REFRESH_INTERVAL_MS = 30_000;

function statusFromString(s?: string): ServiceStatus {
  if (!s) return "unknown";
  const v = s.toLowerCase();
  if (["ok", "up", "operational", "ready", "healthy"].includes(v)) return "operational";
  if (["degraded", "slow"].includes(v)) return "degraded";
  if (["down", "outage", "fail", "failed", "error"].includes(v)) return "outage";
  return "unknown";
}

function buildServices(resp: BackendHealthResp | null): ServiceHealth[] {
  const overall = statusFromString(resp?.status);
  return [
    {
      key: "api",
      name: "API",
      description: "REST + WebSocket gateway",
      icon: Server,
      status: overall === "unknown" ? "operational" : overall,
      uptime90d: 99.94,
    },
    {
      key: "database",
      name: "Database",
      description: "PostgreSQL primary",
      icon: Database,
      status: statusFromString(resp?.database?.status),
      uptime90d: 99.97,
      latencyMs: resp?.database?.latency_ms,
    },
    {
      key: "redis",
      name: "Redis",
      description: "Cache & queue broker",
      icon: Zap,
      status: statusFromString(resp?.redis?.status),
      uptime90d: 99.96,
      latencyMs: resp?.redis?.latency_ms,
    },
    {
      key: "vector",
      name: "Vector store",
      description: "RAG embeddings backend",
      icon: HardDrive,
      status: statusFromString(resp?.vector_store?.status),
      uptime90d: 99.91,
      latencyMs: resp?.vector_store?.latency_ms,
    },
    {
      key: "llm",
      name: "LLM provider",
      description: resp?.llm?.provider ? `Provider: ${resp.llm.provider}` : "Default model API",
      icon: Cpu,
      status: statusFromString(resp?.llm?.status),
      uptime90d: 99.87,
    },
    {
      key: "stripe",
      name: "Stripe API",
      description: "Billing & payments",
      icon: Wifi,
      status: statusFromString(resp?.stripe?.status),
      uptime90d: 99.99,
    },
    {
      key: "worker",
      name: "Background worker",
      description: "Document ingestion + sync jobs",
      icon: Activity,
      status: statusFromString(resp?.worker?.status),
      uptime90d: 99.89,
    },
  ];
}

const STATUS_PILL: Record<ServiceStatus, string> = {
  operational: "pix-pill pix-completed",
  degraded: "pix-pill pix-running",
  outage: "pix-pill pix-failed",
  unknown: "pix-pill",
};

const STATUS_LABEL: Record<ServiceStatus, string> = {
  operational: "Operational",
  degraded: "Degraded",
  outage: "Outage",
  unknown: "Unknown",
};

const STATUS_DOT: Record<ServiceStatus, string> = {
  operational: "var(--pix-up)",
  degraded: "var(--pix-gold)",
  outage: "var(--pix-red)",
  unknown: "var(--pix-idle)",
};

export default function SystemHealthPage() {
  const [resp, setResp] = useState<BackendHealthResp | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [auto, setAuto] = useState(true);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const ready = await apiClient
        .get<BackendHealthResp>("/health/ready")
        .catch(() => null);
      const data = ready ?? (await apiClient.get<BackendHealthResp>("/health"));
      setResp(data);
      setLastChecked(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch health");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (!auto) return;
    const id = window.setInterval(load, REFRESH_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [auto]);

  const services = useMemo(() => buildServices(resp), [resp]);
  const overall: ServiceStatus = useMemo(() => {
    if (services.some((s) => s.status === "outage")) return "outage";
    if (services.some((s) => s.status === "degraded")) return "degraded";
    if (services.every((s) => s.status === "operational" || s.status === "unknown"))
      return "operational";
    return "unknown";
  }, [services]);

  const overallText =
    overall === "operational"
      ? "All systems operational"
      : overall === "outage"
        ? "Active outage"
        : overall === "degraded"
          ? "Degraded performance"
          : "Status unknown";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="pix-mono" style={{ fontSize: 13, color: "var(--pix-ink-soft)", letterSpacing: "0.1em", textTransform: "uppercase" }}>
            System health
          </p>
          <p className="pix-mono" style={{ fontSize: 12, color: "var(--pix-ink-soft)", marginTop: 2 }}>
            Live readiness for each backing service. Auto-refreshes every 30s.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <PixelButton
            variant={auto ? "green" : "default"}
            onClick={() => setAuto((a) => !a)}
          >
            <span
              style={{
                display: "inline-block",
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: auto ? STATUS_DOT.operational : "var(--pix-idle)",
                marginRight: 6,
                animation: auto ? "pix-blink 1.6s steps(2) infinite" : "none",
              }}
            />
            Auto-refresh {auto ? "on" : "off"}
          </PixelButton>
          <PixelButton onClick={load}>
            <RefreshCw className="h-3.5 w-3.5" style={{ animation: loading ? "spin 1s linear infinite" : "none" }} />
            Refresh
          </PixelButton>
        </div>
      </div>

      {/* Overall banner */}
      <PixelFrame>
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                width: 44,
                height: 44,
                border: "3px solid var(--pix-wood-dark)",
                background: "var(--pix-parch-2)",
              }}
            >
              {overall === "outage" ? (
                <AlertCircle className="h-5 w-5" style={{ color: "var(--pix-red)" }} />
              ) : (
                <CheckCircle2 className="h-5 w-5" style={{ color: overall === "operational" ? "var(--pix-up)" : "var(--pix-gold)" }} />
              )}
            </span>
            <div>
              <p className="pix-mono" style={{ fontSize: 12, color: "var(--pix-ink-soft)", letterSpacing: "0.1em", textTransform: "uppercase" }}>
                Overall
              </p>
              <p style={{ fontFamily: '"Pixelify Sans", sans-serif', fontSize: 22, color: "var(--pix-ink)", margin: 0, lineHeight: 1.2 }}>
                {overallText}
              </p>
            </div>
          </div>
          {lastChecked && (
            <span className="pix-mono" style={{ fontSize: 12, color: "var(--pix-ink-soft)" }}>
              Checked {lastChecked.toLocaleTimeString()}
            </span>
          )}
        </div>
      </PixelFrame>

      {/* Per-service grid */}
      {loading && !resp ? (
        <PixelFrame variant="screen">
          <div className="pix-empty" style={{ color: "#9bdbaa" }}>Loading health status…</div>
        </PixelFrame>
      ) : error ? (
        <PixelFrame>
          <div className="pix-empty" style={{ color: "var(--pix-red)" }}>
            <AlertCircle className="mx-auto mb-2 h-6 w-6" />
            Couldn&apos;t fetch health
            <p className="pix-mono" style={{ fontSize: 13, marginTop: 4 }}>{error}</p>
          </div>
        </PixelFrame>
      ) : (
        <div className="pix-grid-cards">
          {services.map((s) => (
            <PixelFrame key={s.key} tight>
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3">
                  <span
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      justifyContent: "center",
                      width: 34,
                      height: 34,
                      background: "var(--pix-parch-3)",
                      border: "2px solid var(--pix-wood-dark)",
                      flexShrink: 0,
                    }}
                  >
                    <s.icon className="h-4 w-4" style={{ color: "var(--pix-ink)" }} />
                  </span>
                  <div>
                    <p style={{ fontFamily: '"Pixelify Sans", sans-serif', fontSize: 15, color: "var(--pix-ink)", lineHeight: 1.2 }}>{s.name}</p>
                    <p className="pix-mono" style={{ fontSize: 12, color: "var(--pix-ink-soft)" }}>{s.description}</p>
                  </div>
                </div>
                <span className={STATUS_PILL[s.status]}>
                  <span
                    aria-hidden
                    style={{
                      display: "inline-block",
                      width: 7,
                      height: 7,
                      borderRadius: "50%",
                      background: STATUS_DOT[s.status],
                      marginRight: 4,
                      animation: s.status === "operational" ? "pix-blink 1.6s steps(2) infinite" : "none",
                    }}
                  />
                  {STATUS_LABEL[s.status]}
                </span>
              </div>
              <div
                className="pix-mono"
                style={{
                  marginTop: 10,
                  paddingTop: 8,
                  borderTop: "2px solid var(--pix-parch-line)",
                  fontSize: 11,
                  letterSpacing: "0.08em",
                  textTransform: "uppercase",
                  color: "var(--pix-ink-soft)",
                  display: "flex",
                  justifyContent: "space-between",
                }}
              >
                <span>{s.uptime90d.toFixed(2)}% · 90d</span>
                {typeof s.latencyMs === "number" && <span>p50 {s.latencyMs}ms</span>}
              </div>
            </PixelFrame>
          ))}
        </div>
      )}

      <p className="pix-mono" style={{ fontSize: 11, color: "var(--pix-ink-soft)", letterSpacing: "0.08em", textTransform: "uppercase" }}>
        Backend wishlist: <code style={{ background: "var(--pix-parch-3)", padding: "0 4px" }}>/health/ready</code> with per-service detail.
        90d uptime is currently illustrative.
      </p>
    </div>
  );
}
