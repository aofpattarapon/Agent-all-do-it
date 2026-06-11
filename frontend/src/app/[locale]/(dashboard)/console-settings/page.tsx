"use client";

import React from "react";
import { toast } from "sonner";
import { useRouter } from "next/navigation";
import { useConsolePrefs, type TimeRange } from "@/components/console/use-console-prefs";
import { useAuthStore } from "@/stores";
import { ROUTES } from "@/lib/constants";
import { PixelButton, PixelFrame, PixelSegmented, PixelToggle, SectionLabel } from "@/components/pixel-ui";

interface ToggleRowProps {
  label: string;
  desc: string;
  on: boolean;
  onChange: (next: boolean) => void;
}
function ToggleRow({ label, desc, on, onChange }: ToggleRowProps) {
  return (
    <div className="pix-set-row">
      <div className="pix-k">
        {label}
        <small>{desc}</small>
      </div>
      <PixelToggle on={on} onChange={onChange} aria-label={label} />
    </div>
  );
}

const RANGE_OPTIONS: { value: TimeRange; label: string }[] = [
  { value: "today", label: "Today" },
  { value: "week", label: "Week" },
  { value: "month", label: "Month" },
  { value: "all", label: "All" },
];

const pixelButtonStyle: React.CSSProperties = {
  background: "transparent",
  border: "2px solid var(--pix-border, #8b6914)",
  cursor: "pointer",
  textAlign: "left",
  padding: "6px 12px",
  fontFamily: '"VT323", monospace',
  fontSize: 16,
  color: "var(--pix-ink)",
  borderRadius: 2,
  width: "100%",
};

export default function ConsoleSettingsPage() {
  const router = useRouter();
  const { user } = useAuthStore();
  const { prefs, update, reset } = useConsolePrefs();

  return (
    <>
      <PixelFrame tight>
        <div className="pix-greet">
          <div>
            <div className="pix-eyebrow">Console</div>
            <h2>⚙️ Settings</h2>
          </div>
        </div>
      </PixelFrame>

      {/* Account */}
      <PixelFrame>
        <SectionLabel>Account</SectionLabel>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <button onClick={() => router.push(ROUTES.PROFILE)} style={pixelButtonStyle}>
            👤 My Profile
          </button>
          {user?.role === "admin" && (
            <button onClick={() => router.push(ROUTES.ADMIN)} style={pixelButtonStyle}>
              🛡️ Admin Panel
            </button>
          )}
        </div>
      </PixelFrame>

      {/* Appearance */}
      <PixelFrame>
        <SectionLabel>Appearance</SectionLabel>
        <ToggleRow
          label="Animations"
          desc="Blinking dots, slide-ins, pulses"
          on={prefs.animations}
          onChange={(v) => update("animations", v)}
        />
        <ToggleRow
          label="Evening light"
          desc="Warm vignette over the console"
          on={prefs.eveningLight}
          onChange={(v) => update("eveningLight", v)}
        />
      </PixelFrame>

      {/* Dashboard */}
      <PixelFrame>
        <SectionLabel>Dashboard</SectionLabel>
        <div className="pix-set-row">
          <div className="pix-k">
            Default time range
            <small>Window for stats, chart &amp; feed</small>
          </div>
          <PixelSegmented<TimeRange>
            options={RANGE_OPTIONS}
            value={prefs.defaultRange}
            onChange={(v) => update("defaultRange", v)}
          />
        </div>
        <ToggleRow
          label="Show The Team"
          desc="Agent status dots in the sidebar"
          on={prefs.showTeam}
          onChange={(v) => update("showTeam", v)}
        />
        <ToggleRow
          label="Show Activity Log"
          desc="Recent runs feed in the sidebar"
          on={prefs.showActivity}
          onChange={(v) => update("showActivity", v)}
        />
      </PixelFrame>

      <PixelFrame tight>
        <div className="pix-set-row" style={{ borderBottom: "none" }}>
          <div className="pix-k">
            Reset preferences
            <small>Restore all console settings to defaults</small>
          </div>
          <PixelButton
            variant="gold"
            onClick={() => {
              reset();
              toast.success("Console preferences reset");
            }}
          >
            ↻ Reset
          </PixelButton>
        </div>
      </PixelFrame>
    </>
  );
}
