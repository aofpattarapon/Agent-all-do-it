"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Bell,
  Palette,
  Shield,
  Slash,
  UserCircle,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  description: string;
}

const ITEMS: NavItem[] = [
  {
    label: "Profile",
    href: "/settings/profile",
    icon: UserCircle,
    description: "Avatar, name, email, sessions",
  },
  {
    label: "Account",
    href: "/settings/account",
    icon: Shield,
    description: "Password, two-factor, danger zone",
  },
  {
    label: "Slash commands",
    href: "/settings/slash-commands",
    icon: Slash,
    description: "Custom shortcuts + built-in toggles",
  },
  {
    label: "Notifications",
    href: "/settings/notifications",
    icon: Bell,
    description: "What we email you about",
  },
  {
    label: "Appearance",
    href: "/settings/appearance",
    icon: Palette,
    description: "Theme, density, brand color",
  },
];

export function SettingsNav() {
  const pathname = usePathname();
  const stripped = pathname.replace(/^\/[a-z]{2}/, "");

  return (
    <>
      {/* Desktop: vertical sidebar nav */}
      <nav
        className="pix-root hidden lg:block"
        style={{
          background: "var(--pix-parch)",
          border: "3px solid var(--pix-wood-dark)",
          padding: "8px",
        }}
      >
        <ul className="space-y-1">
          {ITEMS.map((item) => {
            const active = stripped === item.href || stripped.startsWith(item.href + "/");
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className={cn("group flex items-start gap-3 px-3 py-2.5 transition-colors")}
                  style={{
                    background: active ? "var(--pix-wood-dark)" : "transparent",
                    color: active ? "var(--pix-parch)" : "var(--pix-ink)",
                    fontFamily: '"VT323", monospace',
                    fontSize: "17px",
                    border: active ? "2px solid var(--pix-wood)" : "2px solid transparent",
                  }}
                >
                  <item.icon
                    className="mt-0.5 h-4 w-4 shrink-0"
                    style={{ color: active ? "var(--pix-parch)" : "var(--pix-ink-soft)" }}
                  />
                  <div className="min-w-0">
                    <p style={{ fontFamily: '"Pixelify Sans", sans-serif', fontSize: "14px", fontWeight: 600 }}>
                      {item.label}
                    </p>
                    <p
                      style={{
                        fontFamily: '"VT323", monospace',
                        fontSize: "13px",
                        color: active ? "var(--pix-parch-2)" : "var(--pix-ink-soft)",
                        marginTop: "1px",
                      }}
                    >
                      {item.description}
                    </p>
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Mobile: horizontal scrollable pill tabs */}
      <nav className="pix-root scrollbar-thin -mx-3 flex gap-1.5 overflow-x-auto px-3 pb-2 lg:hidden">
        {ITEMS.map((item) => {
          const active = stripped === item.href || stripped.startsWith(item.href + "/");
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
