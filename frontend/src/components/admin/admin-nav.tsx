"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  Bot,
  FolderKanban,
  LayoutDashboard,
  MessageSquare,
  Rocket,
  Star,
  Users,
  Settings2,
  TrendingUp,
  Workflow,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  description?: string;
}

const ITEMS: NavItem[] = [
  { label: "Overview", href: "/admin", icon: LayoutDashboard },
  { label: "Users", href: "/admin/users", icon: Users },
  { label: "Conversations", href: "/admin/conversations", icon: MessageSquare },
  { label: "Projects", href: "/admin/projects", icon: FolderKanban },
  { label: "Agents", href: "/admin/agents", icon: Bot },
  { label: "Workflows", href: "/admin/workflows", icon: Workflow },
  { label: "Ratings", href: "/admin/ratings", icon: Star },
  { label: "System health", href: "/admin/system", icon: Activity },
  { label: "AI Backend", href: "/admin/settings", icon: Settings2 },
  { label: "Trading Mode", href: "/admin/trading-mode", icon: TrendingUp },
  { label: "Setup", href: "/admin/setup", icon: Rocket },
];

export function AdminNav() {
  const pathname = usePathname();
  const stripped = pathname.replace(/^\/[a-z]{2}/, "");

  return (
    <>
      {/* Desktop: vertical sidebar */}
      <nav
        className="pix-root hidden lg:block"
        style={{
          background: "var(--pix-parch)",
          border: "3px solid var(--pix-wood-dark)",
          padding: "8px",
        }}
      >
        <p
          style={{
            fontFamily: '"VT323", monospace',
            fontSize: "12px",
            letterSpacing: "0.15em",
            textTransform: "uppercase",
            color: "var(--pix-ink-soft)",
            padding: "4px 12px 8px",
          }}
        >
          ⚔ Admin
        </p>
        <ul className="space-y-0.5">
          {ITEMS.map((item) => {
            const active =
              item.href === "/admin"
                ? stripped === "/admin"
                : stripped === item.href || stripped.startsWith(item.href + "/");
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className={cn("group flex items-center gap-2.5 px-3 py-2 transition-colors")}
                  style={{
                    fontFamily: '"Pixelify Sans", sans-serif',
                    fontSize: "13px",
                    fontWeight: 600,
                    background: active ? "var(--pix-wood-dark)" : "transparent",
                    color: active ? "var(--pix-parch)" : "var(--pix-ink)",
                    border: active ? "2px solid var(--pix-wood)" : "2px solid transparent",
                  }}
                >
                  <item.icon
                    className="h-4 w-4 shrink-0"
                    style={{ color: active ? "var(--pix-parch)" : "var(--pix-ink-soft)" }}
                  />
                  <span>{item.label}</span>
                  {active && (
                    <span
                      aria-hidden
                      className="ml-auto h-1.5 w-1.5"
                      style={{ background: "var(--pix-gold)", borderRadius: 0 }}
                    />
                  )}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Mobile: horizontal pill scroll */}
      <nav className="pix-root scrollbar-thin -mx-3 flex gap-1.5 overflow-x-auto px-3 pb-2 lg:hidden">
        {ITEMS.map((item) => {
          const active =
            item.href === "/admin"
              ? stripped === "/admin"
              : stripped === item.href || stripped.startsWith(item.href + "/");
          return (
            <Link
              key={item.href}
              href={item.href}
              className="inline-flex shrink-0 items-center gap-2 px-4 py-1.5 transition-colors"
              style={{
                fontFamily: '"Pixelify Sans", sans-serif',
                fontSize: "13px",
                fontWeight: 600,
                border: "2px solid var(--pix-wood-dark)",
                background: active ? "var(--pix-wood-dark)" : "var(--pix-parch)",
                color: active ? "var(--pix-parch)" : "var(--pix-ink)",
              }}
            >
              <item.icon className="h-3.5 w-3.5" />
              {item.label}
            </Link>
          );
        })}
      </nav>
    </>
  );
}
