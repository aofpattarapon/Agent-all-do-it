"use client";

import { useEffect, useMemo, useState } from "react";
import { CreditCard, MessageSquare, Sparkles, Users } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { toast } from "sonner";

import { SettingsSection } from "@/components/settings/settings-section";

interface NotificationCategory {
  key: string;
  label: string;
  description: string;
  icon: LucideIcon;
  /** Default values for new users. */
  defaults: { email: boolean; inApp: boolean };
}

const CATEGORIES: NotificationCategory[] = [
  {
    key: "billing",
    label: "Billing",
    description: "Subscription renewals, payment failures, low credit warnings.",
    icon: CreditCard,
    defaults: { email: true, inApp: true },
  },
  {
    key: "members",
    label: "Team activity",
    description: "Invitations accepted, members joining or leaving your workspace.",
    icon: Users,
    defaults: { email: true, inApp: true },
  },
  {
    key: "security",
    label: "Security alerts",
    description: "New device sign-ins, password changes, suspicious activity.",
    icon: MessageSquare,
    defaults: { email: true, inApp: true },
  },
  {
    key: "product",
    label: "Product updates",
    description: "New features, release notes, occasional how-to tips.",
    icon: Sparkles,
    defaults: { email: false, inApp: true },
  },
];

const STORAGE_KEY = "settings.notifications.prefs";

type Prefs = Record<string, { email: boolean; inApp: boolean }>;

function defaultPrefs(): Prefs {
  return Object.fromEntries(
    CATEGORIES.map((c) => [c.key, { email: c.defaults.email, inApp: c.defaults.inApp }]),
  );
}

function loadPrefs(): Prefs {
  if (typeof window === "undefined") return defaultPrefs();
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return defaultPrefs();
    return { ...defaultPrefs(), ...(JSON.parse(raw) as Prefs) };
  } catch {
    return defaultPrefs();
  }
}

function savePrefs(prefs: Prefs) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
}

export default function NotificationsSettingsPage() {
  const [prefs, setPrefs] = useState<Prefs>(defaultPrefs);
  const [dirty, setDirty] = useState(false);
  const initialPrefs = useMemo(loadPrefs, []);

  useEffect(() => {
    setPrefs(initialPrefs);
  }, [initialPrefs]);

  const toggle = (key: string, channel: "email" | "inApp") => {
    setPrefs((prev) => ({
      ...prev,
      [key]: {
        email: prev[key]?.email ?? true,
        inApp: prev[key]?.inApp ?? true,
        [channel]: !(prev[key]?.[channel] ?? true),
      },
    }));
    setDirty(true);
  };

  const handleSave = () => {
    savePrefs(prefs);
    toast.success("Notification preferences saved");
    setDirty(false);
  };

  const handleReset = () => {
    setPrefs(defaultPrefs());
    setDirty(true);
  };

  return (
    <div className="space-y-6">
      <SettingsSection
        title="Notification preferences"
        description="Pick which events we send by email versus only show in-app."
        action={
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="pix-btn"
              onClick={handleReset}
              style={{ fontSize: "13px", padding: "5px 10px" }}
            >
              Reset
            </button>
            <button
              type="button"
              className="pix-btn pix-green"
              onClick={handleSave}
              disabled={!dirty}
              style={{ fontSize: "13px", padding: "5px 10px" }}
            >
              Save
            </button>
          </div>
        }
      >
        <div className="pix-frame" style={{ padding: 0, overflow: "hidden" }}>
          {/* Header row */}
          <div
            className="grid items-center gap-2 px-4 py-3"
            style={{
              gridTemplateColumns: "1fr 80px 80px",
              borderBottom: "3px solid var(--pix-wood-dark)",
              background: "var(--pix-parch-3)",
            }}
          >
            <span
              style={{
                fontFamily: '"VT323", monospace',
                fontSize: "13px",
                letterSpacing: "0.1em",
                textTransform: "uppercase",
                color: "var(--pix-ink-soft)",
              }}
            >
              Category
            </span>
            <span
              className="text-center"
              style={{
                fontFamily: '"VT323", monospace',
                fontSize: "13px",
                letterSpacing: "0.1em",
                textTransform: "uppercase",
                color: "var(--pix-ink-soft)",
              }}
            >
              Email
            </span>
            <span
              className="text-center"
              style={{
                fontFamily: '"VT323", monospace',
                fontSize: "13px",
                letterSpacing: "0.1em",
                textTransform: "uppercase",
                color: "var(--pix-ink-soft)",
              }}
            >
              In-app
            </span>
          </div>

          {/* Rows */}
          <ul style={{ display: "flex", flexDirection: "column" }}>
            {CATEGORIES.map((c, idx) => {
              const p = prefs[c.key] ?? c.defaults;
              const enabled = p.email || p.inApp;
              return (
                <li
                  key={c.key}
                  className="grid items-center gap-2 px-4 py-3"
                  style={{
                    gridTemplateColumns: "1fr 80px 80px",
                    borderBottom:
                      idx < CATEGORIES.length - 1 ? "2px solid var(--pix-parch-line)" : "none",
                    background: enabled ? undefined : "rgba(0,0,0,0.02)",
                  }}
                >
                  <div className="flex min-w-0 items-start gap-3">
                    <span
                      className="inline-flex h-9 w-9 shrink-0 items-center justify-center"
                      style={{
                        background: enabled ? "var(--pix-parch-3)" : "var(--pix-parch-line)",
                        border: "2px solid var(--pix-wood-dark)",
                        color: enabled ? "var(--pix-ink)" : "var(--pix-ink-soft)",
                      }}
                    >
                      <c.icon size={16} />
                    </span>
                    <div className="min-w-0">
                      <p
                        style={{
                          fontFamily: '"Pixelify Sans", sans-serif',
                          fontSize: "14px",
                          fontWeight: 600,
                          color: "var(--pix-ink)",
                        }}
                      >
                        {c.label}
                      </p>
                      <p
                        style={{
                          fontFamily: '"VT323", monospace',
                          fontSize: "13px",
                          color: "var(--pix-ink-soft)",
                          lineHeight: 1.3,
                        }}
                      >
                        {c.description}
                      </p>
                    </div>
                  </div>
                  <div className="flex justify-center">
                    <Toggle checked={p.email} onChange={() => toggle(c.key, "email")} />
                  </div>
                  <div className="flex justify-center">
                    <Toggle checked={p.inApp} onChange={() => toggle(c.key, "inApp")} />
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
        <p
          className="mt-4"
          style={{
            fontFamily: '"VT323", monospace',
            fontSize: "13px",
            color: "var(--pix-ink-soft)",
            lineHeight: 1.4,
          }}
        >
          Preferences are stored locally for now. Backend wiring required (
          <code
            style={{
              fontFamily: '"VT323", monospace',
              background: "var(--pix-parch-3)",
              padding: "0 4px",
            }}
          >
            /users/me/notifications
          </code>
          ) to sync across devices.
        </p>
      </SettingsSection>
    </div>
  );
}

function Toggle({ checked, onChange }: { checked: boolean; onChange: () => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={onChange}
      className={"pix-toggle " + (checked ? "pix-on" : "")}
    >
      <span aria-hidden className="pix-knob" />
    </button>
  );
}
