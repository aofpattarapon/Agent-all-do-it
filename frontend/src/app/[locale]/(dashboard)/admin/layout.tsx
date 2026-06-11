import type { ReactNode } from "react";

export default function AdminLayout({ children }: { children: ReactNode }) {
  return (
    <div
      className="pix-root mx-auto w-full max-w-7xl space-y-6 pb-10"
      style={{ background: "var(--pix-parch)", minHeight: "100%" }}
    >
      {/* Pixel-themed admin header */}
      <div className="pix-frame" style={{ padding: "20px 24px" }}>
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
          ⚔ Admin · power-user tools
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
          Operate the <em style={{ color: "var(--pix-gold)", fontStyle: "italic" }}>workspace.</em>
        </h1>
        <div className="mt-2 flex items-center gap-3">
          <p
            style={{
              fontFamily: '"VT323", monospace',
              fontSize: "15px",
              color: "var(--pix-ink-soft)",
              flex: 1,
            }}
          >
            Users, conversations, ratings, billing webhooks, system health — all in one place.
          </p>
          <span
            className="inline-flex items-center gap-2 px-3 py-1"
            style={{
              fontFamily: '"VT323", monospace',
              fontSize: "12px",
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              border: "2px solid var(--pix-gold-dark)",
              background: "var(--pix-parch-2)",
              color: "var(--pix-gold-dark)",
            }}
          >
            <span
              aria-hidden
              className="h-1.5 w-1.5 animate-pulse rounded-full"
              style={{ background: "var(--pix-gold-dark)" }}
            />
            Admin role required
          </span>
        </div>
      </div>

      <div className="min-w-0">{children}</div>
    </div>
  );
}

