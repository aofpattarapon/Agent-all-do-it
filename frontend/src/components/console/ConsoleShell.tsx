"use client";

import type { ReactNode } from "react";
import { useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { formatDistanceToNow } from "date-fns";
import {
  LayoutGrid,
  Settings2,
  FolderKanban,
  Clock,
  Shield,
  ChevronDown,
  ChevronRight,
  User,
  Palette,
  Monitor,
  Slash,
  Bell,
  LayoutDashboard,
  Users,
  MessageSquare,
  Bot,
  Workflow,
  Star,
  Activity,
  BookOpen,
  DollarSign,
  GitBranch,
  TrendingUp,
  Zap,
  ScrollText,
  CandlestickChart,
} from "lucide-react";
import { ROUTES } from "@/lib/constants";
import { useAuthStore } from "@/stores";
import {
  ActivityFeed,
  PixelFrame,
  PixelNavButton,
  SectionLabel,
  Sparkline,
  type ActivityItem,
} from "@/components/pixel-ui";
import { useConsoleData, sortByRecency } from "./use-console-data";
import { useConsolePrefs } from "./use-console-prefs";

export type NavId = "overview" | "projects" | "rooms" | "history" | "order-history" | "settings" | "profile" | "admin" | "tutorial" | "cost" | "skill-versions" | "learning-loop" | "notifications" | "triggers" | "trade-floor" | "system-logs";

interface ConsoleShellProps {
  /**
   * Active nav item. Optional — when omitted, derived from the current
   * pathname (locale-stripped) so the shell works as an app-wide layout.
   */
  active?: NavId;
  /** When false, hides the sidebar Team card. Defaults to console prefs. */
  showTeam?: boolean;
  /** When false, hides the sidebar Activity Log card. Defaults to console prefs. */
  showActivity?: boolean;
  /** Disable animations (adds .pix-no-anim). Defaults to console prefs. */
  animations?: boolean;
  children: ReactNode;
}

/** Strip a leading `/xx` locale segment from a pathname. */
function stripLocale(pathname: string): string {
  return pathname.replace(/^\/[a-z]{2}(?=\/|$)/, "") || "/";
}

/** Derive the active nav id from a locale-stripped pathname. */
function navIdFromPath(path: string): NavId | undefined {
  if (path === ROUTES.DASHBOARD) return "overview";
  if (path === "/history") return "history";
  if (path === "/order-history") return "order-history";
  if (path === "/tutorial") return "tutorial";
  if (path === "/cost-dashboard") return "cost";
  if (path === "/skill-versions") return "skill-versions";
  if (path === "/learning-loop") return "learning-loop";
  if (path === "/notification-center") return "notifications";
  if (path === "/trigger-registry") return "triggers";
  if (path === "/console-settings" || path.startsWith("/settings/")) return "settings";
  if (path.startsWith("/projects/") && path.endsWith("/trade-floor")) return "trade-floor";
  if (path === "/system-logs") return "system-logs";
  if (path.startsWith("/projects/") && (path.endsWith("/handoffs") || path.endsWith("/secrets") || path.endsWith("/integrations") || path.endsWith("/vault"))) return "projects";
  if (path === ROUTES.PROFILE || path.startsWith(ROUTES.PROFILE + "/")) return "settings";
  if (path === ROUTES.ADMIN || path.startsWith(ROUTES.ADMIN + "/")) return "admin";
  if (path === ROUTES.PROJECTS || path.startsWith(ROUTES.PROJECTS + "/")) {
    // A project room counts as "rooms"; anything else under projects is "projects".
    return path.includes("/room") ? "rooms" : "projects";
  }
  return undefined;
}

function statusToKind(status: string): "up" | "down" | "plain" {
  if (status === "completed") return "up";
  if (status === "failed") return "down";
  return "plain";
}

function statusToIcon(status: string): string {
  if (status === "completed") return "✅";
  if (status === "failed") return "🔻";
  if (status === "running") return "▶";
  return "•";
}

function relTime(run: { started_at: string | null; finished_at: string | null }): string {
  const ts = run.finished_at ?? run.started_at;
  if (!ts) return "—";
  try {
    return formatDistanceToNow(new Date(ts), { addSuffix: true });
  } catch {
    return "—";
  }
}

function isPathActive(pathname: string, path: string) {
  const stripped = pathname.replace(/^\/[a-z]{2}(?=\/|$)/, "") || "/";
  return stripped === path || stripped.startsWith(path + "/");
}

function SettingsNav({ resolvedActive, pathname }: { resolvedActive: NavId | undefined; pathname: string }) {
  const router = useRouter();
  const [expanded, setExpanded] = useState(
    resolvedActive === "settings" ||
    resolvedActive === "profile"
  );
  const isActive = resolvedActive === "settings" || resolvedActive === "profile";

  const items = [
    { id: "profile", label: "Profile", icon: <User size={14} />, path: "/settings/profile" },
    { id: "account", label: "Account", icon: <Settings2 size={14} />, path: "/settings/account" },
    { id: "appearance", label: "Appearance", icon: <Palette size={14} />, path: "/settings/appearance" },
    { id: "slash", label: "Slash commands", icon: <Slash size={14} />, path: "/settings/slash-commands" },
    { id: "notifications", label: "Notifications", icon: <Bell size={14} />, path: "/settings/notifications" },
    { id: "console", label: "Console", icon: <Monitor size={14} />, path: "/console-settings" },
  ];

  return (
    <div>
      <button
        className={"pix-nav-btn " + (isActive ? "pix-active" : "")}
        onClick={() => setExpanded((v) => !v)}
        style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}
      >
        <span style={{ display: "flex", alignItems: "center", gap: 11 }}>
          <Settings2 size={17} /> Settings
        </span>
        {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
      </button>
      {expanded && (
        <div className="pix-nav-sub">
          {items.map((item) => {
            const active = isPathActive(pathname, item.path);
            return (
              <button
                key={item.id}
                className={"pix-nav-sub-btn " + (active ? "pix-active" : "")}
                onClick={() => router.push(item.path)}
              >
                <span style={{ display: "flex", alignItems: "center", gap: 9 }}>
                  {item.icon} {item.label}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function AdminNavShell({ resolvedActive, user, pathname }: { resolvedActive: NavId | undefined; user: { role?: string } | null; pathname: string }) {
  const router = useRouter();
  const [expanded, setExpanded] = useState(resolvedActive === "admin");
  const isActive = resolvedActive === "admin";
  if (user?.role !== "admin") return null;

  const items = [
    { id: "overview", label: "Overview", icon: <LayoutDashboard size={14} />, path: "/admin" },
    { id: "users", label: "Users", icon: <Users size={14} />, path: "/admin/users" },
    { id: "conversations", label: "Conversations", icon: <MessageSquare size={14} />, path: "/admin/conversations" },
    { id: "projects", label: "Projects", icon: <FolderKanban size={14} />, path: "/admin/projects" },
    { id: "agents", label: "Agents", icon: <Bot size={14} />, path: "/admin/agents" },
    { id: "workflows", label: "Workflows", icon: <Workflow size={14} />, path: "/admin/workflows" },
    { id: "ratings", label: "Ratings", icon: <Star size={14} />, path: "/admin/ratings" },
    { id: "system", label: "System health", icon: <Activity size={14} />, path: "/admin/system" },
    { id: "ai", label: "AI Backend", icon: <Settings2 size={14} />, path: "/admin/settings" },
  ];

  return (
    <div>
      <button
        className={"pix-nav-btn " + (isActive ? "pix-active" : "")}
        onClick={() => setExpanded((v) => !v)}
        style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}
      >
        <span style={{ display: "flex", alignItems: "center", gap: 11 }}>
          <Shield size={17} /> Admin
        </span>
        {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
      </button>
      {expanded && (
        <div className="pix-nav-sub">
          {items.map((item) => {
            const active = isPathActive(pathname, item.path);
            return (
              <button
                key={item.id}
                className={"pix-nav-sub-btn " + (active ? "pix-active" : "")}
                onClick={() => router.push(item.path)}
              >
                <span style={{ display: "flex", alignItems: "center", gap: 9 }}>
                  {item.icon} {item.label}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function ConsoleShell({
  active,
  showTeam = true,
  showActivity = true,
  animations = true,
  children,
}: ConsoleShellProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { user } = useAuthStore();
  const { projects, team, allRuns, totalProjects, totalAgents, totalRuns, workflowHealth } = useConsoleData();

  // Derive the active nav id from pathname when not explicitly provided
  const strippedPath = stripLocale(pathname);
  const resolvedActive: NavId | undefined = active ?? navIdFromPath(strippedPath);

  const running = useMemo(() => allRuns.some((r) => r.status === "running"), [allRuns]);

  const recentRuns = useMemo(() => sortByRecency(allRuns).slice(0, 10), [allRuns]);

  const feed: ActivityItem[] = useMemo(
    () =>
      recentRuns.map((r) => ({
        id: r.id,
        ic: statusToIcon(r.status),
        text: r.workflow_name ?? r.trigger ?? "Run",
        who: r.projectName,
        kind: statusToKind(r.status),
        time: relTime(r),
      })),
    [recentRuns],
  );

  // Sparkline: count of runs per day over the last 14 days.
  const spark = useMemo(() => {
    const days = 14;
    const buckets = new Array<number>(days).fill(0);
    const now = Date.now();
    const dayMs = 86_400_000;
    allRuns.forEach((r) => {
      const ts = r.started_at ?? r.finished_at;
      if (!ts) return;
      const diff = Math.floor((now - new Date(ts).getTime()) / dayMs);
      if (diff >= 0 && diff < days) {
        const idx = days - 1 - diff;
        buckets[idx] = (buckets[idx] ?? 0) + 1;
      }
    });
    return buckets;
  }, [allRuns]);

  return (
    <div className={"pix-root" + (animations ? "" : " pix-no-anim")}>
      <div className="pix-console">
        <aside className="pix-sidebar">
          {/* Brand */}
          <PixelFrame tight>
            <div className="pix-brand">
              <div className="pix-ava">🌱</div>
              <div>
                <h1>PIXEL DREAM</h1>
                <div className="pix-sub">
                  <span
                    className="pix-status-dot"
                    style={{ background: running ? "var(--pix-up)" : "var(--pix-gold)" }}
                  />
                  {running ? "agents on the floor" : "console idle"}
                </div>
              </div>
            </div>
          </PixelFrame>

          {/* Nav */}
          <PixelFrame tight>
            <nav className="pix-nav">
              <SectionLabel>Overview</SectionLabel>
              <PixelNavButton
                icon={<LayoutGrid size={17} />}
                label="Overview"
                active={resolvedActive === "overview"}
                onClick={() => router.push(ROUTES.DASHBOARD)}
              />

              <SectionLabel>Project</SectionLabel>
              <PixelNavButton
                icon={<FolderKanban size={17} />}
                label="Projects"
                active={resolvedActive === "projects"}
                onClick={() => router.push(ROUTES.PROJECTS)}
              />

              <SectionLabel>Log</SectionLabel>
              <PixelNavButton
                icon={<Clock size={17} />}
                label="History"
                active={resolvedActive === "history"}
                onClick={() => router.push("/history")}
              />

              <SectionLabel>Tutorial</SectionLabel>
              <PixelNavButton
                icon={<BookOpen size={17} />}
                label="Tutorial"
                active={resolvedActive === "tutorial"}
                onClick={() => router.push("/tutorial")}
              />

              <SectionLabel>Monitor</SectionLabel>
              <PixelNavButton
                icon={<DollarSign size={17} />}
                label="Cost"
                active={resolvedActive === "cost"}
                onClick={() => router.push("/cost-dashboard")}
              />
              <PixelNavButton
                icon={<GitBranch size={17} />}
                label="Skill Versions"
                active={resolvedActive === "skill-versions"}
                onClick={() => router.push("/skill-versions")}
              />
              <PixelNavButton
                icon={<TrendingUp size={17} />}
                label="Learning Loop (All)"
                active={resolvedActive === "learning-loop"}
                onClick={() => router.push("/learning-loop")}
              />
              <PixelNavButton
                icon={<Bell size={17} />}
                label="Notifications"
                active={resolvedActive === "notifications"}
                onClick={() => router.push("/notification-center")}
              />
              <PixelNavButton
                icon={<Zap size={17} />}
                label="Triggers"
                active={resolvedActive === "triggers"}
                onClick={() => router.push("/trigger-registry")}
              />
              <PixelNavButton
                icon={<CandlestickChart size={17} />}
                label="Order History (All)"
                active={resolvedActive === "order-history"}
                onClick={() => router.push("/order-history")}
              />
              <PixelNavButton
                icon={<ScrollText size={17} />}
                label="System Logs (All)"
                active={resolvedActive === "system-logs"}
                onClick={() => router.push("/system-logs")}
              />

              <SectionLabel>Setting</SectionLabel>
              <SettingsNav resolvedActive={resolvedActive} pathname={pathname} />

              {user?.role === "admin" ? <SectionLabel>Admin</SectionLabel> : null}
              <AdminNavShell resolvedActive={resolvedActive} user={user} pathname={pathname} />
            </nav>
          </PixelFrame>

          {/* Rooms */}
          <PixelFrame tight>
            <SectionLabel>Rooms</SectionLabel>
            {projects.length === 0 ? (
              <div className="pix-mono pix-muted" style={{ fontSize: 11, padding: "4px 0" }}>No rooms yet.</div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                {projects.slice(0, 8).map((p) => (
                  <button
                    key={p.id}
                    onClick={() => router.push(`/projects/${p.id}#office`)}
                    style={{
                      background: "transparent",
                      border: "none",
                      cursor: "pointer",
                      textAlign: "left",
                      padding: "4px 6px",
                      fontFamily: '"VT323", monospace',
                      fontSize: 14,
                      color: "var(--pix-ink)",
                      borderRadius: 2,
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(0,0,0,0.08)")}
                    onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                  >
                    🏠 {p.name.length > 14 ? p.name.slice(0, 14) + "…" : p.name}
                  </button>
                ))}
              </div>
            )}
          </PixelFrame>

          {/* Live stats */}
          <PixelFrame>
            <SectionLabel>Live Stats</SectionLabel>
            <div className="pix-stats">
              <div className="pix-stat">
                <span className="pix-k">Projects</span>
                <span className="pix-v">{totalProjects}</span>
              </div>
              <div className="pix-stat">
                <span className="pix-k">Agents</span>
                <span className="pix-v">{totalAgents}</span>
              </div>
              <div className="pix-stat">
                <span className="pix-k">Runs</span>
                <span className="pix-v">{totalRuns}</span>
              </div>
              <div className="pix-stat">
                <span className="pix-k">Health</span>
                <span className={"pix-v " + (workflowHealth >= 50 ? "pix-up" : "pix-down")}>
                  {totalRuns === 0 ? "—" : `${workflowHealth}%`}
                </span>
              </div>
            </div>
            <Sparkline data={spark} />
          </PixelFrame>

          {/* The Team */}
          {showTeam && (
            <PixelFrame tight>
              <SectionLabel>The Team</SectionLabel>
              {team.length === 0 ? (
                <div className="pix-mono pix-muted">No agents yet.</div>
              ) : (
                <div className="pix-team">
                  {team.slice(0, 15).map((m) => (
                    <div className="pix-teammate" key={m.id} title={`${m.name} · ${m.projectName} — ${m.status}`}>
                      <div className="pix-tm-face">
                        🤖
                        <span
                          className={
                            "pix-tm-dot" +
                            (m.status === "running"
                              ? " pix-on"
                              : m.status === "done"
                                ? " pix-done"
                                : m.status === "error"
                                  ? " pix-error"
                                  : "")
                          }
                        />
                      </div>
                      <div className="pix-tm-name">{m.name}</div>
                    </div>
                  ))}
                </div>
              )}
            </PixelFrame>
          )}

          {/* Activity log */}
          {showActivity && (
            <PixelFrame>
              <SectionLabel>Activity Log</SectionLabel>
              <ActivityFeed items={feed} emptyText="Waiting for the first run…" />
            </PixelFrame>
          )}
          {user?.email && (
            <PixelFrame tight>
              <div className="pix-mono" style={{ fontSize: 11, padding: "4px 0", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={user.email}>
                {user.email}
              </div>
            </PixelFrame>
          )}
        </aside>

        <main className="pix-main">{children}</main>
      </div>
    </div>
  );
}
