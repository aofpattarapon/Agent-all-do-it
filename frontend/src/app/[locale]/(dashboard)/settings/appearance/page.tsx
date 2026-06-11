"use client";

import { BrandColorPicker } from "@/components/settings/brand-color-picker";
import { SettingsRow, SettingsSection } from "@/components/settings/settings-section";
import { ThemeToggle } from "@/components/theme";

export default function AppearanceSettingsPage() {
  return (
    <div className="space-y-6">
      <SettingsSection title="Theme" description="Light, dark, or follow your system preference.">
        <SettingsRow
          label="Color scheme"
          description="Affects the entire dashboard. Marketing pages alternate sections regardless."
          control={<ThemeToggle variant="dropdown" />}
        />
      </SettingsSection>

      <SettingsSection
        title="Brand color"
        description="Pick the accent color used across the workspace. Saved per-device."
      >
        <BrandColorPicker />
        <div
          className="mt-5 p-4"
          style={{
            border: "2px solid var(--pix-parch-line)",
            background: "var(--pix-parch-2)",
          }}
        >
          <p
            style={{
              fontFamily: '"VT323", monospace',
              fontSize: "13px",
              color: "var(--pix-ink-soft)",
              lineHeight: 1.4,
            }}
          >
            Choosing a preset updates CSS custom properties at runtime —{" "}
            <code
              style={{
                fontFamily: '"VT323", monospace',
                background: "var(--pix-parch-3)",
                padding: "0 4px",
                fontSize: "12px",
              }}
            >
              --brand-h
            </code>
            ,{" "}
            <code
              style={{
                fontFamily: '"VT323", monospace',
                background: "var(--pix-parch-3)",
                padding: "0 4px",
                fontSize: "12px",
              }}
            >
              --brand-c
            </code>
            ,{" "}
            <code
              style={{
                fontFamily: '"VT323", monospace',
                background: "var(--pix-parch-3)",
                padding: "0 4px",
                fontSize: "12px",
              }}
            >
              --brand-l
            </code>
            . Forking the template lets you bake any color in by editing one block in{" "}
            <code
              style={{
                fontFamily: '"VT323", monospace',
                background: "var(--pix-parch-3)",
                padding: "0 4px",
                fontSize: "12px",
              }}
            >
              globals.css
            </code>
            .
          </p>
        </div>
      </SettingsSection>
    </div>
  );
}
