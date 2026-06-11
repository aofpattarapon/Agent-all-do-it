"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Activity,
  ArrowUpRight,
  CreditCard,
  MessageSquare,
  RefreshCw,
  Rocket,
  Star,
  UserPlus,
  Users,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { PixelButton, PixelFrame } from "@/components/pixel-ui";
import { apiClient } from "@/lib/api-client";

interface AdminStats {
  total_users?: number;
  active_users_24h?: number;
  total_conversations?: number;
  total_messages?: number;
  credits_charged_30d?: number;
  mrr_cents?: number;
}

interface RecentEvent {
  id: string;
  type: "user_signup" | "conversation_created" | "subscription_renewed" | "rating_low";
  title: string;
  description: string;
  timestamp: string;
}

const EVENT_ICON: Record<RecentEvent["type"], LucideIcon> = {
  user_signup: UserPlus,
  conversation_created: MessageSquare,
  subscription_renewed: CreditCard,
  rating_low: Star,
};

function formatRelative(iso: string): string {
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "";
  const diff = Math.round((Date.now() - t) / 1000);
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export default function AdminOverviewPage() {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(true);
  const [events, setEvents] = useState<RecentEvent[] | null>(null);

  const loadStats = async () => {
    setStatsLoading(true);
    try {
      const data = await apiClient.get<AdminStats>("/admin/stats").catch(() => null);
      if (data) {
        setStats(data);
      } else {
        const [usersResp, convsResp] = await Promise.allSettled([
          apiClient.get<{ total: number }>("/admin/users?limit=1"),
          apiClient.get<{ total: number }>("/admin/conversations?limit=1"),
        ]);
        setStats({
          total_users: usersResp.status === "fulfilled" ? usersResp.value.total : undefined,
          total_conversations: convsResp.status === "fulfilled" ? convsResp.value.total : undefined,
        });
      }
    } finally {
      setStatsLoading(false);
    }
  };

  const loadEvents = async () => {
    setEvents(null);
    try {
      const events = await apiClient
        .get<{ items: RecentEvent[] }>("/admin/events")
        .catch(() => null);
      if (events) {
        setEvents(events.items.slice(0, 8));
        return;
      }
      const convs = await apiClient
        .get<{
          items: Array<{ id: string; user_email?: string; title?: string; created_at: string }>;
        }>("/admin/conversations?limit=8")
        .catch(() => ({ items: [] }));
      setEvents(
        convs.items.map((c) => ({
          id: c.id,
          type: "conversation_created" as const,
          title: c.title || "New conversation",
          description: c.user_email ? `by ${c.user_email}` : "",
          timestamp: c.created_at,
        })),
      );
    } catch {
      setEvents([]);
    }
  };

  useEffect(() => {
    loadStats();
    loadEvents();
  }, []);

  return (
    <div className="pix-root space-y-6">
      <div className="flex items-end justify-between gap-3">
        <div>
          <p
            style={{
              fontFamily: '"VT323", monospace',
              fontSize: "12px",
              letterSpacing: "0.15em",
              textTransform: "uppercase",
              color: "var(--pix-ink-soft)",
            }}
          >
            Overview
          </p>
          <h2
            style={{
              fontFamily: '"Pixelify Sans", sans-serif',
              fontSize: "20px",
              fontWeight: 700,
              color: "var(--pix-gold-dark)",
              marginTop: "2px",
            }}
          >
            The view from <em style={{ color: "var(--pix-gold)", fontStyle: "italic" }}>above.</em>
          </h2>
        </div>
        <PixelButton
          onClick={() => {
            loadStats();
            loadEvents();
          }}
        >
          <RefreshCw className="h-3.5 w-3.5" style={{ animation: statsLoading ? "spin 1s linear infinite" : "none" }} />
          Refresh
        </PixelButton>
      </div>

      {/* Stats strip */}
      {statsLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <PixelFrame key={i} tight style={{ opacity: 0.6 }}>
              <div style={{ height: 60, display: "flex", alignItems: "center", justifyContent: "center" }}>
                <span className="pix-mono pix-muted" style={{ fontSize: 14 }}>Loading…</span>
              </div>
            </PixelFrame>
          ))}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <PixelStat label="Total users" value={(stats?.total_users ?? 0).toLocaleString()} icon={Users} />
          <PixelStat label="Active 24h" value={(stats?.active_users_24h ?? 0).toLocaleString()} icon={Activity} featured />
          <PixelStat label="Conversations" value={(stats?.total_conversations ?? 0).toLocaleString()} icon={MessageSquare} />
          <PixelStat
            label="MRR"
            value={
              typeof stats?.mrr_cents === "number"
                ? (stats.mrr_cents / 100).toLocaleString("en-US", {
                    style: "currency",
                    currency: "USD",
                    minimumFractionDigits: 0,
                  })
                : "—"
            }
            icon={CreditCard}
          />
        </div>
      )}

      {/* Quick actions */}
      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <QuickLink
          href="/admin/users"
          icon={Users}
          title="Manage users"
          description="Search, suspend, impersonate"
        />
        <QuickLink
          href="/admin/conversations"
          icon={MessageSquare}
          title="Browse chats"
          description="All conversations across users"
        />
        <QuickLink
          href="/admin/stripe-events"
          icon={CreditCard}
          title="Stripe events"
          description="Replay webhooks, debug billing"
        />
        <QuickLink
          href="/admin/system"
          icon={Activity}
          title="System health"
          description="Per-service status & uptime"
        />
        <QuickLink
          href="/admin/ratings"
          icon={Star}
          title="Response ratings"
          description="Quality signals from users"
        />
        <QuickLink
          href="/admin/setup"
          icon={Rocket}
          title="Setup wizard"
          description="Seed agents, skills, and configure"
        />
      </section>

      {/* Recent activity */}
      <PixelFrame style={{ padding: 0, overflow: "hidden" }}>
        <div
          className="flex items-center justify-between px-6 py-5"
          style={{ borderBottom: "2px solid var(--pix-parch-line)" }}
        >
          <div>
            <h2
              style={{
                fontFamily: '"Pixelify Sans", sans-serif',
                fontSize: "16px",
                fontWeight: 700,
                color: "var(--pix-gold-dark)",
              }}
            >
              Recent activity
            </h2>
            <p
              style={{
                fontFamily: '"VT323", monospace',
                fontSize: "14px",
                color: "var(--pix-ink-soft)",
              }}
            >
              Workspace-wide events.
            </p>
          </div>
        </div>
        {events === null ? (
          <div className="p-6">
            {[1, 2, 3, 4, 5].map((i) => (
              <div
                key={i}
                className="flex items-center gap-3 px-6 py-4"
                style={{ borderBottom: "1px solid var(--pix-parch-line)", opacity: 0.5 }}
              >
                <span
                  className="inline-flex h-9 w-9 shrink-0 items-center justify-center"
                  style={{ background: "var(--pix-parch-2)", border: "2px solid var(--pix-parch-line)" }}
                />
                <div className="min-w-0 flex-1 space-y-2">
                  <div style={{ height: 14, width: "30%", background: "var(--pix-parch-line)" }} />
                  <div style={{ height: 12, width: "60%", background: "var(--pix-parch-line)" }} />
                </div>
              </div>
            ))}
          </div>
        ) : events.length === 0 ? (
          <div className="m-6 p-10 text-center" style={{ border: "2px dashed var(--pix-parch-line)" }}>
            <p
              style={{
                fontFamily: '"VT323", monospace',
                fontSize: "16px",
                color: "var(--pix-ink-soft)",
              }}
            >
              No recent events.
            </p>
          </div>
        ) : (
          <ul style={{ borderTop: "none" }}>
            {events.map((e) => {
              const Icon = EVENT_ICON[e.type] ?? MessageSquare;
              return (
                <li
                  key={e.id}
                  className="flex items-center gap-3 px-6 py-4"
                  style={{ borderBottom: "1px solid var(--pix-parch-line)" }}
                >
                  <span
                    className="inline-flex h-9 w-9 shrink-0 items-center justify-center"
                    style={{
                      background: "var(--pix-parch-2)",
                      color: "var(--pix-ink)",
                      border: "2px solid var(--pix-parch-line)",
                    }}
                  >
                    <Icon className="h-4 w-4" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p
                      className="truncate"
                      style={{
                        fontFamily: '"Pixelify Sans", sans-serif',
                        fontSize: "14px",
                        fontWeight: 600,
                        color: "var(--pix-ink)",
                      }}
                    >
                      {e.title}
                    </p>
                    <p
                      className="truncate"
                      style={{
                        fontFamily: '"VT323", monospace',
                        fontSize: "13px",
                        color: "var(--pix-ink-soft)",
                      }}
                    >
                      {e.description}
                      {e.description && " · "}
                      {formatRelative(e.timestamp)}
                    </p>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </PixelFrame>
    </div>
  );
}

function PixelStat({
  label,
  value,
  icon: Icon,
  featured,
}: {
  label: string;
  value: string | number;
  icon: LucideIcon;
  featured?: boolean;
}) {
  return (
    <PixelFrame tight style={{ background: featured ? "var(--pix-green-deep)" : undefined }}>
      <div className="flex items-start justify-between">
        <p
          style={{
            fontFamily: '"VT323", monospace',
            fontSize: "12px",
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            color: featured ? "var(--pix-screen-dim)" : "var(--pix-ink-soft)",
          }}
        >
          {label}
        </p>
        {Icon && <Icon className="h-4 w-4" style={{ color: featured ? "var(--pix-screen)" : "var(--pix-ink-soft)", opacity: 0.7 }} />}
      </div>
      <div className="mt-2">
        <span
          style={{
            fontFamily: '"VT323", monospace',
            fontSize: "28px",
            fontWeight: 700,
            color: featured ? "var(--pix-screen)" : "var(--pix-ink)",
            lineHeight: 1,
          }}
        >
          {value}
        </span>
      </div>
    </PixelFrame>
  );
}

function QuickLink({
  href,
  icon: Icon,
  title,
  description,
}: {
  href: string;
  icon: LucideIcon;
  title: string;
  description: string;
}) {
  return (
    <Link
      href={href}
      className="pix-frame group flex items-center gap-3 p-4 transition-all"
      style={{ textDecoration: "none" }}
    >
      <span
        className="inline-flex h-9 w-9 shrink-0 items-center justify-center transition-colors"
        style={{
          background: "var(--pix-parch-2)",
          color: "var(--pix-ink)",
          border: "2px solid var(--pix-wood-dark)",
        }}
      >
        <Icon className="h-4 w-4" />
      </span>
      <div className="min-w-0 flex-1">
        <p
          style={{
            fontFamily: '"Pixelify Sans", sans-serif',
            fontSize: "13px",
            fontWeight: 700,
            color: "var(--pix-ink)",
          }}
        >
          {title}
        </p>
        <p
          className="truncate"
          style={{
            fontFamily: '"VT323", monospace',
            fontSize: "13px",
            color: "var(--pix-ink-soft)",
          }}
        >
          {description}
        </p>
      </div>
      <ArrowUpRight
        className="h-4 w-4 transition-all group-hover:rotate-45"
        style={{ color: "var(--pix-ink-soft)" }}
      />
    </Link>
  );
}
