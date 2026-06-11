"use client";

import Image from "next/image";
import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Camera, CandlestickChart, Globe, Monitor, Smartphone, Target, Trash2, TrendingUp } from "lucide-react";
import { toast } from "sonner";

import { SettingsSection } from "@/components/settings/settings-section";
import { SectionLabel, StatCard } from "@/components/pixel-ui";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
  Button,
  Input,
  Label,
} from "@/components/ui";
import { useAuth } from "@/hooks";
import { apiClient, ApiError } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores";
import type { Session, SessionListResponse, User } from "@/types";

interface TradingPerformance {
  total_trades: number;
  wins: number;
  losses: number;
  winrate_pct: number;
  total_pnl_usdt: number;
}

interface ProjectItem {
  id: string;
  name: string;
}

interface ProjectList {
  items: ProjectItem[];
  total: number;
}

function formatMoney(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)} USDT`;
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function DeviceIcon({ type }: { type?: string | null }) {
  if (type === "mobile") return <Smartphone className="h-4 w-4" />;
  if (type === "desktop") return <Monitor className="h-4 w-4" />;
  return <Globe className="h-4 w-4" />;
}

function TradingSummary() {
  const { data: summary } = useQuery({
    queryKey: ["profile", "trading-summary"],
    queryFn: async () => {
      const projects = await apiClient.get<ProjectList>("/projects");
      const items = projects.items ?? [];
      if (items.length === 0) return null;

      const results = await Promise.all(
        items.map(async (p) => {
          try {
            const perf = await apiClient.get<TradingPerformance>(`/projects/${p.id}/trading/performance`);
            return { ...perf, projectId: p.id, projectName: p.name };
          } catch {
            return null;
          }
        }),
      );

      const valid = results.filter((r): r is TradingPerformance & { projectId: string; projectName: string } => Boolean(r));
      if (valid.length === 0) return null;

      const totalTrades = valid.reduce((sum, r) => sum + (r.total_trades ?? 0), 0);
      const totalPnl = valid.reduce((sum, r) => sum + (r.total_pnl_usdt ?? 0), 0);
      const best = valid.reduce((best, r) => (r.winrate_pct > best.winrate_pct ? r : best), valid[0]!);

      return {
        totalTrades,
        totalPnl,
        bestProject: best!.projectName,
        bestWinrate: best!.winrate_pct,
      };
    },
  });

  if (!summary) return null;

  return (
    <SettingsSection
      title="Demo Trading Performance (Binance Testnet)"
      description="Aggregated stats across all your projects."
    >
      <div className="grid gap-3 md:grid-cols-3">
        <StatCard
          label="Total Trades"
          value={summary.totalTrades}
          icon={<TrendingUp className="h-4 w-4" />}
        />
        <StatCard
          label="Total PnL"
          value={formatMoney(summary.totalPnl)}
          icon={<CandlestickChart className="h-4 w-4" />}
          trend={summary.totalPnl >= 0 ? "up" : "down"}
        />
        <StatCard
          label="Best Win Rate"
          value={`${summary.bestWinrate.toFixed(1)}%`}
          icon={<Target className="h-4 w-4" />}
          sub={summary.bestProject}
        />
      </div>
    </SettingsSection>
  );
}

export default function ProfileSettingsPage() {
  const { user } = useAuth();
  const { setUser } = useAuthStore();

  const [name, setName] = useState(user?.full_name ?? "");
  const [email, setEmail] = useState(user?.email ?? "");
  const [saving, setSaving] = useState(false);
  const [avatarUploading, setAvatarUploading] = useState(false);
  const avatarInputRef = useRef<HTMLInputElement>(null);

  const [sessions, setSessions] = useState<Session[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  // Backend may not have a sessions endpoint when `enable_session_management`
  // is off (stateless JWT). Track availability so we can hide the whole section
  // instead of showing a misleading "no data" placeholder.
  const [sessionsAvailable, setSessionsAvailable] = useState(true);

  useEffect(() => {
    setName(user?.full_name ?? "");
    setEmail(user?.email ?? "");
  }, [user?.id, user?.email, user?.full_name]);

  const fetchSessions = useCallback(async () => {
    try {
      const data = await apiClient.get<SessionListResponse>("/sessions");
      setSessions(data.sessions);
      setSessionsAvailable(true);
    } catch (err) {
      // 404 = endpoint not exposed (session management disabled at gen time).
      if (err instanceof ApiError && err.status === 404) {
        setSessionsAvailable(false);
      }
    } finally {
      setSessionsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  const handleSaveProfile = async () => {
    if (!user) return;
    setSaving(true);
    try {
      const payload: { email?: string; full_name?: string | null } = {};
      if (email !== user.email) payload.email = email;
      if (name !== (user.full_name ?? "")) payload.full_name = name || null;
      if (Object.keys(payload).length === 0) {
        toast.info("Nothing changed");
        setSaving(false);
        return;
      }
      const updated = await apiClient.patch<User>("/users/me", payload);
      setUser(updated);
      toast.success("Profile updated");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Failed to update profile");
    } finally {
      setSaving(false);
    }
  };

  const handleAvatarUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";
    if (file.size > 2 * 1024 * 1024) {
      toast.error("Avatar too large. Maximum 2MB.");
      return;
    }
    setAvatarUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch("/api/users/me/avatar", { method: "POST", body: formData });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Upload failed" }));
        throw new Error(err.detail || "Upload failed");
      }
      const updated = await res.json();
      setUser(updated);
      toast.success("Avatar updated");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to upload avatar");
    } finally {
      setAvatarUploading(false);
    }
  };

  const handleRevokeSession = async (sessionId: string) => {
    try {
      await apiClient.delete(`/sessions/${sessionId}`);
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
      toast.success("Session revoked");
    } catch {
      toast.error("Failed to revoke session");
    }
  };

  const handleRevokeAll = async () => {
    try {
      await apiClient.delete("/sessions");
      setSessions((prev) => prev.filter((s) => s.is_current));
      toast.success("All other sessions revoked");
    } catch {
      toast.error("Failed to revoke sessions");
    }
  };

  if (!user) {
    return null;
  }

  return (
    <div className="pix-root space-y-6">
      <SettingsSection
        title="Avatar"
        description="Square images look best. Up to 2MB. JPG, PNG, WEBP, or GIF."
      >
        <div className="flex items-center gap-5">
          <button
            type="button"
            onClick={() => avatarInputRef.current?.click()}
            disabled={avatarUploading}
            className="group relative flex h-24 w-24 shrink-0 items-center justify-center overflow-hidden transition-all"
            style={{
              border: "3px solid var(--pix-wood-dark)",
              background: "var(--pix-parch-2)",
              boxShadow: "0 4px 0 var(--pix-wood-darkest)",
            }}
          >
            {user.avatar_url ? (
              <Image
                src={`/api/users/avatar/${user.id}`}
                alt=""
                width={96}
                height={96}
                className="h-full w-full object-cover"
                unoptimized
              />
            ) : (
              <span
                style={{
                  fontFamily: '"VT323", monospace',
                  fontSize: "24px",
                  fontWeight: 700,
                  color: "var(--pix-ink)",
                }}
              >
                {(user.full_name || user.email).slice(0, 2).toUpperCase()}
              </span>
            )}
            <span className="absolute inset-0 flex items-center justify-center bg-black/50 opacity-0 backdrop-blur-sm transition-opacity group-hover:opacity-100">
              <Camera className="h-5 w-5 text-white" />
            </span>
          </button>
          <input
            ref={avatarInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp,image/gif"
            onChange={handleAvatarUpload}
            className="hidden"
          />
          <div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => avatarInputRef.current?.click()}
              disabled={avatarUploading}
              style={{
                fontFamily: '"Pixelify Sans", sans-serif',
                background: "var(--pix-wood-dark)",
                color: "var(--pix-parch)",
                border: "2px solid var(--pix-wood-darkest)",
                borderRadius: 0,
                boxShadow: "0 3px 0 var(--pix-wood-darkest)",
              }}
            >
              {avatarUploading
                ? "Uploading…"
                : user.avatar_url
                  ? "Replace avatar"
                  : "Upload avatar"}
            </Button>
            <p
              style={{
                fontFamily: '"VT323", monospace',
                fontSize: "13px",
                color: "var(--pix-ink-soft)",
                marginTop: "8px",
              }}
            >
              {user.role === "admin" ? "Admin · " : ""}Member since{" "}
              {user.created_at ? new Date(user.created_at).toLocaleDateString() : "—"}
            </p>
          </div>
        </div>
      </SettingsSection>

      <SettingsSection
        title="Personal info"
        description="Visible to teammates in shared organizations."
        action={
          <Button
            onClick={handleSaveProfile}
            disabled={saving}
            size="sm"
            style={{
              fontFamily: '"Pixelify Sans", sans-serif',
              background: "var(--pix-gold-dark)",
              color: "var(--pix-parch)",
              border: "2px solid var(--pix-wood-darkest)",
              borderRadius: 0,
              boxShadow: "0 3px 0 var(--pix-wood-darkest)",
            }}
          >
            {saving ? "Saving…" : "Save changes"}
          </Button>
        }
      >
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label
              htmlFor="profile-name"
              style={{
                fontFamily: '"VT323", monospace',
                fontSize: "15px",
                letterSpacing: "0.1em",
                textTransform: "uppercase",
                color: "var(--pix-ink)",
              }}
            >
              Display name
            </Label>
            <Input
              id="profile-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="How should we call you?"
              style={{
                background: "var(--pix-parch-2)",
                border: "2px solid var(--pix-wood-dark)",
                borderRadius: 0,
                fontFamily: '"VT323", monospace',
                fontSize: "18px",
                color: "var(--pix-ink)",
                height: "40px",
              }}
            />
          </div>
          <div className="space-y-1.5">
            <Label
              htmlFor="profile-email"
              style={{
                fontFamily: '"VT323", monospace',
                fontSize: "15px",
                letterSpacing: "0.1em",
                textTransform: "uppercase",
                color: "var(--pix-ink)",
              }}
            >
              Email
            </Label>
            <Input
              id="profile-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={{
                background: "var(--pix-parch-2)",
                border: "2px solid var(--pix-wood-dark)",
                borderRadius: 0,
                fontFamily: '"VT323", monospace',
                fontSize: "18px",
                color: "var(--pix-ink)",
                height: "40px",
              }}
            />
            <p
              style={{
                fontFamily: '"VT323", monospace',
                fontSize: "13px",
                color: "var(--pix-ink-soft)",
              }}
            >
              Changing email may require re-verification depending on your auth setup.
            </p>
          </div>
        </div>
      </SettingsSection>

      {sessionsAvailable && (
        <SettingsSection
          title="Active sessions"
          description="Devices currently signed in to your account."
          action={
            sessions.filter((s) => !s.is_current).length > 0 ? (
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button
                    variant="outline"
                    size="sm"
                    style={{
                      fontFamily: '"Pixelify Sans", sans-serif',
                      background: "var(--pix-parch)",
                      color: "var(--pix-ink)",
                      border: "2px solid var(--pix-wood-dark)",
                      borderRadius: 0,
                    }}
                  >
                    Revoke all others
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Revoke all other sessions?</AlertDialogTitle>
                    <AlertDialogDescription>
                      Every device signed in to your account will be signed out, except this one.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction onClick={handleRevokeAll}>Revoke all</AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            ) : null
          }
        >
          {sessionsLoading ? (
            <div className="space-y-2">
              {[1, 2].map((i) => (
                <div
                  key={i}
                  className="h-14 animate-pulse"
                  style={{ background: "var(--pix-parch-2)" }}
                />
              ))}
            </div>
          ) : sessions.length === 0 ? (
            <p style={{ fontFamily: '"VT323", monospace', fontSize: "15px", color: "var(--pix-ink-soft)" }}>
              No session data available.
            </p>
          ) : (
            <ul className="space-y-2">
              {sessions.map((session) => (
                <li
                  key={session.id}
                  className="relative flex items-center justify-between gap-3 px-4 py-3 transition-all"
                  style={{
                    background: session.is_current ? "var(--pix-parch-2)" : "var(--pix-parch)",
                    border: session.is_current
                      ? "2px solid var(--pix-gold-dark)"
                      : "2px solid var(--pix-parch-line)",
                  }}
                >
                  {session.is_current && (
                    <span
                      aria-hidden
                      className="absolute top-1/2 left-0 h-6 w-1 -translate-y-1/2"
                      style={{ background: "var(--pix-gold-dark)" }}
                    />
                  )}
                  <div className="flex min-w-0 items-center gap-3">
                    <span
                      className="inline-flex h-9 w-9 shrink-0 items-center justify-center"
                      style={{
                        background: session.is_current ? "var(--pix-gold-dark)" : "var(--pix-parch-3)",
                        color: session.is_current ? "var(--pix-parch)" : "var(--pix-ink)",
                        border: "2px solid var(--pix-wood-dark)",
                      }}
                    >
                      <DeviceIcon type={session.device_type} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p
                        className="flex items-center gap-2"
                        style={{
                          fontFamily: '"Pixelify Sans", sans-serif',
                          fontSize: "14px",
                          fontWeight: 600,
                          color: "var(--pix-ink)",
                        }}
                      >
                        <span className="truncate">{session.device_name || "Unknown device"}</span>
                        {session.is_current && (
                          <span
                            className="inline-flex items-center gap-1 px-2 py-0.5"
                            style={{
                              fontFamily: '"VT323", monospace',
                              fontSize: "12px",
                              letterSpacing: "0.1em",
                              textTransform: "uppercase",
                              background: "var(--pix-gold)",
                              color: "var(--pix-ink)",
                              border: "1px solid var(--pix-gold-dark)",
                            }}
                          >
                            <span aria-hidden className="h-1 w-1 animate-pulse rounded-full" style={{ background: "var(--pix-ink)" }} />
                            Current
                          </span>
                        )}
                      </p>
                      <p
                        className="truncate"
                        style={{
                          fontFamily: '"VT323", monospace',
                          fontSize: "13px",
                          color: "var(--pix-ink-soft)",
                        }}
                      >
                        {session.ip_address && `${session.ip_address} · `}
                        Last active {timeAgo(session.last_used_at)}
                      </p>
                    </div>
                  </div>
                  {!session.is_current && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-8 shrink-0"
                      style={{ color: "var(--pix-red)" }}
                      onClick={() => handleRevokeSession(session.id)}
                      title="Revoke session"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </SettingsSection>
      )}
      <TradingSummary />
    </div>
  );
}

