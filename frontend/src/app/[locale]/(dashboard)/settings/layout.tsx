import type { ReactNode } from "react";

export default function SettingsLayout({ children }: { children: ReactNode }) {
  return (
    <div
      className="pix-root mx-auto w-full max-w-6xl space-y-6 pb-10"
      style={{ background: "var(--pix-parch)", minHeight: "100%" }}
    >
      {/* Pixel-themed header */}
      <div
        className="pix-frame"
        style={{ padding: "20px 24px" }}
      >
        <p
          style={{
            fontFamily: '"VT323", monospace',
            fontSize: "13px",
            letterSpacing: "0.15em",
            textTransform: "uppercase",
            color: "var(--pix-ink-soft)",
            marginBottom: "4px",
          }}
        >
          ⚙ Settings
        </p>
        <h1
          style={{
            fontFamily: '"Pixelify Sans", sans-serif',
            fontSize: "24px",
            fontWeight: 700,
            color: "var(--pix-gold-dark)",
            margin: 0,
            lineHeight: 1.2,
          }}
        >
          Make it <em style={{ color: "var(--pix-gold)", fontStyle: "italic" }}>yours.</em>
        </h1>
        <p
          style={{
            fontFamily: '"VT323", monospace',
            fontSize: "16px",
            color: "var(--pix-ink-soft)",
            marginTop: "4px",
          }}
        >
          Personal account, appearance, notifications, slash commands.
        </p>
      </div>

      <div className="min-w-0">{children}</div>
    </div>
  );
}
