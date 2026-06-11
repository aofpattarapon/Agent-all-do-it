"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { CheckCircle2, ChevronLeft, Loader2, Rocket, Wallet } from "lucide-react";
import { toast } from "sonner";

import { PixelButton, PixelFrame, PixelToggle } from "@/components/pixel-ui";
import { apiClient } from "@/lib/api-client";
import { useAuth } from "@/hooks/use-auth";
import { Spinner } from "@/components/ui/spinner";

interface Project {
  id: string;
  name: string;
}

interface SeedCryptoResponse {
  ok: boolean;
  project_id: string;
  already_existed: boolean;
}

const TOTAL_STEPS = 5;

export default function AdminSetupPage() {
  const router = useRouter();
  const { user, isLoading: authLoading } = useAuth();

  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [projectId, setProjectId] = useState<string | null>(null);

  // Step 2 state
  const [pipelineExists, setPipelineExists] = useState(false);
  const [checkingProjects, setCheckingProjects] = useState(false);

  // Step 3 state
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [liveTrading, setLiveTrading] = useState(false);

  // Step 4 state
  const [dailyBudget, setDailyBudget] = useState(100);
  const [alertAt, setAlertAt] = useState(80);

  // Admin gate
  useEffect(() => {
    if (!authLoading && user && user.role !== "admin") {
      router.push("/");
    }
  }, [authLoading, user, router]);

  // Step 2: check pipelines on entry
  const checkPipelines = async () => {
    setCheckingProjects(true);
    setError(null);
    try {
      const data = await apiClient.get<{ items: Project[]; total: number }>("/projects");
      const found = data.items.find(
        (p) => p.name === "Binance Testnet — BTCUSDT Pipeline"
      );
      if (found) {
        setPipelineExists(true);
        setProjectId(found.id);
        toast.success("NEXMIND pipeline already configured");
        // Brief pause so the user sees the checkmark, then skip to Step 4
        setTimeout(() => setStep(4), 1200);
      } else {
        setPipelineExists(false);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to load projects";
      setError(msg);
    } finally {
      setCheckingProjects(false);
    }
  };

  const handleStart = () => {
    setStep(2);
    checkPipelines();
  };

  const createPipeline = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiClient.post<SeedCryptoResponse>("/admin/seed/crypto");
      if (data.ok) {
        setProjectId(data.project_id);
        toast.success(data.already_existed ? "Pipeline already exists" : "NEXMIND pipeline created");
        setStep(3);
      } else {
        setError("Failed to create pipeline");
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to create pipeline";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const skipStep = () => {
    setError(null);
    setStep(4);
  };

  const handleSaveTradingConfig = async () => {
    if (!projectId) {
      setError("No project selected");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const secretsList = await apiClient.get<{
        items: { id: string; name: string; provider: string; value_masked: string }[];
        total: number;
      }>(`/projects/${projectId}/secrets`);

      const nameToId = new Map<string, string>();
      for (const s of secretsList.items) {
        nameToId.set(s.name, s.id);
      }

      const secretsToSave = [
        { name: "BINANCE_API_KEY", provider: "binance", value: apiKey.trim() },
        { name: "BINANCE_API_SECRET", provider: "binance", value: apiSecret.trim() },
        { name: "EXCHANGE_MODE", provider: "binance", value: liveTrading ? "live" : "testnet" },
      ];

      for (const secret of secretsToSave) {
        if (!secret.value && secret.name !== "EXCHANGE_MODE") {
          continue; // skip empty key/secret
        }

        const existingId = nameToId.get(secret.name);
        if (existingId) {
          await apiClient.patch(`/projects/${projectId}/secrets/${existingId}`, {
            name: secret.name,
            value: secret.value,
          });
        } else {
          await apiClient.post(`/projects/${projectId}/secrets`, {
            name: secret.name,
            provider: secret.provider,
            value: secret.value,
          });
        }
      }

      toast.success("Trading config saved");
      setStep(4);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to save trading config";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const saveBudget = async () => {
    if (!projectId) {
      setError("No project selected");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await apiClient.patch(
        `/projects/${projectId}/cost/budget?daily_budget_usd=${dailyBudget}&alert_at_pct=${alertAt}`
      );
      toast.success("Budget applied");
      setStep(5);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to apply budget";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const progressPct = (step / TOTAL_STEPS) * 100;

  if (authLoading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <Spinner className="h-8 w-8" style={{ color: "var(--pix-gold-dark)" }} />
      </div>
    );
  }

  if (!user || user.role !== "admin") {
    return null; // redirect handled in useEffect
  }

  return (
    <div className="mx-auto max-w-lg space-y-6 py-8">
      {/* Progress bar */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span
            style={{
              fontFamily: '"VT323", monospace',
              fontSize: "12px",
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              color: "var(--pix-ink-soft)",
            }}
          >
            Setup Wizard
          </span>
          <span
            style={{
              fontFamily: '"VT323", monospace',
              fontSize: "12px",
              color: "var(--pix-ink-soft)",
            }}
          >
            Step {step} of {TOTAL_STEPS}
          </span>
        </div>
        <div
          className="h-2 w-full overflow-hidden rounded-sm"
          style={{ background: "var(--pix-parch-line)", opacity: 0.4 }}
        >
          <div
            className="h-full transition-all duration-500 ease-out"
            style={{
              width: `${progressPct}%`,
              background: "var(--pix-gold-dark)",
            }}
          />
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <PixelFrame variant="wood" tight>
          <div className="p-3" style={{ color: "#b91c1c" }}>
            <p
              style={{
                fontFamily: '"VT323", monospace',
                fontSize: "14px",
              }}
            >
              ⚠ {error}
            </p>
          </div>
        </PixelFrame>
      )}

      {/* Step 1 — Welcome */}
      {step === 1 && (
        <PixelFrame className="text-center">
          <div className="space-y-6 p-6">
            <div
              className="mx-auto flex h-16 w-16 items-center justify-center rounded-full"
              style={{ background: "var(--pix-gold-deep)", border: "2px solid var(--pix-gold-dark)" }}
            >
              <Rocket className="h-8 w-8" style={{ color: "var(--pix-parch)" }} />
            </div>
            <div className="space-y-2">
              <h1
                style={{
                  fontFamily: '"Pixelify Sans", sans-serif',
                  fontSize: "22px",
                  fontWeight: 700,
                  color: "var(--pix-gold-dark)",
                }}
              >
                Welcome to Pixel Dream Agent
              </h1>
              <p
                style={{
                  fontFamily: '"VT323", monospace',
                  fontSize: "16px",
                  color: "var(--pix-ink-soft)",
                  lineHeight: 1.4,
                }}
              >
                This wizard will configure your AI agent pipelines. It only needs to be run once.
              </p>
            </div>
            <PixelButton variant="gold" onClick={handleStart} className="w-full justify-center">
              Start Setup
            </PixelButton>
          </div>
        </PixelFrame>
      )}

      {/* Step 2 — Check Pipelines */}
      {step === 2 && (
        <PixelFrame>
          <div className="space-y-5 p-6">
            <div className="space-y-1">
              <h2
                style={{
                  fontFamily: '"Pixelify Sans", sans-serif',
                  fontSize: "18px",
                  fontWeight: 700,
                  color: "var(--pix-gold-dark)",
                }}
              >
                Check Pipelines
              </h2>
              <p
                style={{
                  fontFamily: '"VT323", monospace',
                  fontSize: "14px",
                  color: "var(--pix-ink-soft)",
                }}
              >
                Verifying whether the NEXMIND crypto pipeline is already seeded…
              </p>
            </div>

            {checkingProjects ? (
              <div className="flex items-center gap-3 py-4">
                <Loader2 className="h-5 w-5 animate-spin" style={{ color: "var(--pix-gold-dark)" }} />
                <span
                  style={{
                    fontFamily: '"VT323", monospace',
                    fontSize: "14px",
                    color: "var(--pix-ink-soft)",
                  }}
                >
                  Checking projects…
                </span>
              </div>
            ) : pipelineExists ? (
              <div className="flex items-center gap-3 py-2">
                <CheckCircle2 className="h-6 w-6" style={{ color: "var(--pix-green-dark)" }} />
                <span
                  style={{
                    fontFamily: '"VT323", monospace',
                    fontSize: "15px",
                    color: "var(--pix-green-dark)",
                  }}
                >
                  NEXMIND pipeline already configured
                </span>
              </div>
            ) : (
              <div className="space-y-4">
                <p
                  style={{
                    fontFamily: '"VT323", monospace',
                    fontSize: "14px",
                    color: "var(--pix-ink)",
                  }}
                >
                  NEXMIND pipeline not found. Click below to create it.
                </p>
                <PixelButton
                  variant="gold"
                  onClick={createPipeline}
                  disabled={loading}
                  className="w-full justify-center"
                >
                  {loading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Rocket className="h-4 w-4" />
                  )}
                  Create NEXMIND Pipeline
                </PixelButton>
              </div>
            )}

            {!checkingProjects && !pipelineExists && (
              <div className="flex justify-start">
                <PixelButton variant="default" onClick={() => setStep(1)} disabled={loading}>
                  <ChevronLeft className="h-4 w-4" />
                  Back
                </PixelButton>
              </div>
            )}
          </div>
        </PixelFrame>
      )}

      {/* Step 3 — Configure Trading */}
      {step === 3 && (
        <PixelFrame>
          <div className="space-y-5 p-6">
            <div className="space-y-1">
              <h2
                style={{
                  fontFamily: '"Pixelify Sans", sans-serif',
                  fontSize: "18px",
                  fontWeight: 700,
                  color: "var(--pix-gold-dark)",
                }}
              >
                Configure Trading
              </h2>
              <p
                style={{
                  fontFamily: '"VT323", monospace',
                  fontSize: "14px",
                  color: "var(--pix-ink-soft)",
                }}
              >
                Configure your Binance API keys for live trading (optional — you can skip for paper trading).
              </p>
            </div>

            <div className="space-y-4">
              <div className="space-y-1">
                <label
                  style={{
                    fontFamily: '"VT323", monospace',
                    fontSize: "13px",
                    color: "var(--pix-ink-soft)",
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
                  }}
                >
                  Binance API Key
                </label>
                <input
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder="••••••••••••••••"
                  className="w-full rounded-sm border px-3 py-2 text-sm outline-none focus:ring-2"
                  style={{
                    fontFamily: '"VT323", monospace',
                    background: "var(--pix-parch)",
                    borderColor: "var(--pix-parch-line)",
                    color: "var(--pix-ink)",
                  }}
                />
              </div>

              <div className="space-y-1">
                <label
                  style={{
                    fontFamily: '"VT323", monospace',
                    fontSize: "13px",
                    color: "var(--pix-ink-soft)",
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
                  }}
                >
                  Binance API Secret
                </label>
                <input
                  type="password"
                  value={apiSecret}
                  onChange={(e) => setApiSecret(e.target.value)}
                  placeholder="••••••••••••••••"
                  className="w-full rounded-sm border px-3 py-2 text-sm outline-none focus:ring-2"
                  style={{
                    fontFamily: '"VT323", monospace',
                    background: "var(--pix-parch)",
                    borderColor: "var(--pix-parch-line)",
                    color: "var(--pix-ink)",
                  }}
                />
              </div>

              <div className="flex items-center justify-between rounded-sm border p-3" style={{ borderColor: "var(--pix-parch-line)" }}>
                <span
                  style={{
                    fontFamily: '"VT323", monospace',
                    fontSize: "14px",
                    color: "var(--pix-ink)",
                  }}
                >
                  Enable Live Trading
                </span>
                <PixelToggle on={liveTrading} onChange={setLiveTrading} aria-label="Enable live trading" />
              </div>

              <p
                style={{
                  fontFamily: '"VT323", monospace',
                  fontSize: "12px",
                  color: "var(--pix-ink-soft)",
                }}
              >
                Leave blank to use paper/testnet trading mode.
              </p>
            </div>

            <div className="flex items-center justify-between gap-3">
              <PixelButton variant="default" onClick={() => setStep(2)} disabled={loading}>
                <ChevronLeft className="h-4 w-4" />
                Back
              </PixelButton>
              <div className="flex gap-2">
                <PixelButton variant="default" onClick={skipStep} disabled={loading}>
                  Skip
                </PixelButton>
                <PixelButton variant="gold" onClick={handleSaveTradingConfig} disabled={loading}>
                  {loading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    "Save & Continue"
                  )}
                </PixelButton>
              </div>
            </div>
          </div>
        </PixelFrame>
      )}

      {/* Step 4 — Set Daily Budget */}
      {step === 4 && (
        <PixelFrame>
          <div className="space-y-5 p-6">
            <div className="space-y-1">
              <h2
                style={{
                  fontFamily: '"Pixelify Sans", sans-serif',
                  fontSize: "18px",
                  fontWeight: 700,
                  color: "var(--pix-gold-dark)",
                }}
              >
                Set Daily Budget
              </h2>
              <p
                style={{
                  fontFamily: '"VT323", monospace',
                  fontSize: "14px",
                  color: "var(--pix-ink-soft)",
                }}
              >
                Set a daily spend limit to prevent runaway agent costs.
              </p>
            </div>

            <div className="space-y-4">
              <div className="space-y-1">
                <label
                  style={{
                    fontFamily: '"VT323", monospace',
                    fontSize: "13px",
                    color: "var(--pix-ink-soft)",
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
                  }}
                >
                  Daily Budget (USD)
                </label>
                <input
                  type="number"
                  min={1}
                  value={dailyBudget}
                  onChange={(e) => setDailyBudget(Number(e.target.value))}
                  className="w-full rounded-sm border px-3 py-2 text-sm outline-none focus:ring-2"
                  style={{
                    fontFamily: '"VT323", monospace',
                    background: "var(--pix-parch)",
                    borderColor: "var(--pix-parch-line)",
                    color: "var(--pix-ink)",
                  }}
                />
              </div>

              <div className="space-y-1">
                <label
                  style={{
                    fontFamily: '"VT323", monospace',
                    fontSize: "13px",
                    color: "var(--pix-ink-soft)",
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
                  }}
                >
                  Alert at (%)
                </label>
                <input
                  type="number"
                  min={1}
                  max={99}
                  value={alertAt}
                  onChange={(e) => setAlertAt(Number(e.target.value))}
                  className="w-full rounded-sm border px-3 py-2 text-sm outline-none focus:ring-2"
                  style={{
                    fontFamily: '"VT323", monospace',
                    background: "var(--pix-parch)",
                    borderColor: "var(--pix-parch-line)",
                    color: "var(--pix-ink)",
                  }}
                />
              </div>
            </div>

            <div className="flex items-center justify-between gap-3">
              <PixelButton variant="default" onClick={() => setStep(pipelineExists ? 2 : 3)} disabled={loading}>
                <ChevronLeft className="h-4 w-4" />
                Back
              </PixelButton>
              <PixelButton
                variant="gold"
                onClick={saveBudget}
                disabled={loading}
                className="justify-center"
              >
                {loading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Wallet className="h-4 w-4" />
                )}
                Apply Budget
              </PixelButton>
            </div>
          </div>
        </PixelFrame>
      )}

      {/* Step 5 — Done */}
      {step === 5 && (
        <PixelFrame className="text-center">
          <div className="space-y-6 p-6">
            <div
              className="mx-auto flex h-16 w-16 items-center justify-center rounded-full"
              style={{
                background: "var(--pix-green-deep)",
                border: "2px solid var(--pix-green-dark)",
              }}
            >
              <CheckCircle2 className="h-8 w-8" style={{ color: "var(--pix-parch)" }} />
            </div>
            <div className="space-y-2">
              <h2
                style={{
                  fontFamily: '"Pixelify Sans", sans-serif',
                  fontSize: "20px",
                  fontWeight: 700,
                  color: "var(--pix-green-dark)",
                }}
              >
                Setup Complete
              </h2>
              <p
                style={{
                  fontFamily: '"VT323", monospace',
                  fontSize: "16px",
                  color: "var(--pix-ink-soft)",
                  lineHeight: 1.4,
                }}
              >
                Your 12-agent NEXMIND pipeline is ready.
              </p>
            </div>
            <PixelButton
              variant="gold"
              onClick={() => router.push("/")}
              className="w-full justify-center"
            >
              Go to Dashboard
            </PixelButton>
          </div>
        </PixelFrame>
      )}
    </div>
  );
}
