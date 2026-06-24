"use client";

// Renders the execution-mode badge + TP/SL protection block for a position.
//
// Background: TP/SL is placed as SEPARATE reduce-only orders on the exchange (an SL
// stop_market order + up to three TP limit orders), NOT as Binance position-level TP/SL.
// Binance's own position row therefore may not show TP/SL — but the orders exist under
// Open Orders, and this block is the app's source of truth for grouped visibility.

// ── Types (mirror backend app/services/execution_visibility.py output) ──────────

export interface ProtectionOrderRow {
  price: number | null;
  order_id: string | null;
  status: string;
}

export interface TakeProfitRow {
  level: number;
  price: number | null;
  order_id: string | null;
  status: string;
}

export type ProtectionStatus = "ACTIVE" | "PARTIAL" | "MISSING" | "CLOSED" | "UNKNOWN";

export interface Protection {
  status: ProtectionStatus;
  source: string;
  explanation: string;
  stop_loss: ProtectionOrderRow | null;
  take_profits: TakeProfitRow[];
  sl_active: boolean;
  tp_active_count: number;
  tp_total_count: number;
}

export interface ExecutionVisibility {
  safety_mode: string;
  exchange_route: string | null;
  execution_mode_label: string;
  submitted_to_exchange: boolean;
  simulated_only: boolean;
  real_money: boolean;
  protection: Protection;
}

// ── Style helpers ───────────────────────────────────────────────────────────

const STATUS_TONE: Record<ProtectionStatus, string> = {
  ACTIVE: "var(--pix-success, #4ade80)",
  PARTIAL: "var(--pix-gold, #fbbf24)",
  MISSING: "var(--pix-danger, #f87171)",
  CLOSED: "var(--pix-muted, #9ca3af)",
  UNKNOWN: "var(--pix-muted, #9ca3af)",
};

const STATUS_LABEL: Record<ProtectionStatus, string> = {
  ACTIVE: "PROTECTED",
  PARTIAL: "PARTIAL PROTECTION",
  MISSING: "NO TP/SL",
  CLOSED: "CLOSED",
  UNKNOWN: "UNKNOWN",
};

/** Color the execution-mode badge: red for real money, green-ish for simulated/demo. */
function modeTone(v: ExecutionVisibility): string {
  if (v.real_money) return "var(--pix-danger, #f87171)";
  if (v.simulated_only) return "var(--pix-muted, #9ca3af)";
  return "var(--pix-success, #4ade80)"; // demo / testnet — submitted to exchange, no real money
}

function fmtPrice(n: number | null): string {
  return n === null || n === undefined ? "—" : String(n);
}

function shortId(id: string | null): string {
  if (!id) return "—";
  return id.length > 14 ? `${id.slice(0, 6)}…${id.slice(-4)}` : id;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function PositionProtection({ visibility }: { visibility: ExecutionVisibility | null | undefined }) {
  if (!visibility) return null;
  const p = visibility.protection;
  const tone = STATUS_TONE[p.status] ?? STATUS_TONE.UNKNOWN;

  const rowStyle = { fontFamily: '"VT323", monospace', fontSize: 13 } as const;
  const idStyle = { opacity: 0.7, fontSize: 12 } as const;

  return (
    <div className="mt-1 space-y-1" style={rowStyle} data-testid="position-protection">
      <div className="flex flex-wrap items-center gap-2">
        {/* True execution mode — replaces the old misleading "PAPER" label */}
        <span
          className="pix-pill"
          style={{ color: modeTone(visibility), borderColor: modeTone(visibility) }}
          title={
            visibility.real_money
              ? "Real-money order route."
              : visibility.simulated_only
                ? "Simulated only — no order placed on an exchange."
                : "Submitted to the exchange in a non-real-money mode (demo/testnet)."
          }
          data-testid="execution-mode-badge"
        >
          {visibility.execution_mode_label}
        </span>
        {visibility.exchange_route && (
          <span className="pix-row-sub" style={{ opacity: 0.7 }}>
            {visibility.exchange_route}
          </span>
        )}
        <span
          className="pix-pill"
          style={{ color: tone, borderColor: tone }}
          data-testid="protection-status"
        >
          {STATUS_LABEL[p.status] ?? p.status}
        </span>
      </div>

      {/* SL row */}
      {p.stop_loss && (
        <div className="flex flex-wrap items-center gap-2" data-testid="protection-sl">
          <span style={{ color: "var(--pix-danger, #f87171)" }}>SL</span>
          <span>{fmtPrice(p.stop_loss.price)}</span>
          <span style={idStyle}>order {shortId(p.stop_loss.order_id)}</span>
          <span style={idStyle}>· {p.stop_loss.status}</span>
        </div>
      )}

      {/* TP rows */}
      {p.take_profits.map((tp) => (
        <div
          key={tp.level}
          className="flex flex-wrap items-center gap-2"
          data-testid={`protection-tp-${tp.level}`}
        >
          <span style={{ color: "var(--pix-success, #4ade80)" }}>TP{tp.level}</span>
          <span>{fmtPrice(tp.price)}</span>
          <span style={idStyle}>order {shortId(tp.order_id)}</span>
          <span style={idStyle}>· {tp.status}</span>
        </div>
      ))}

      {/* Explanation / tooltip text — clarifies the separate reduce-only order model */}
      <p
        className="pix-row-sub"
        style={{ opacity: 0.7, fontSize: 12 }}
        title={p.explanation}
        data-testid="protection-explanation"
      >
        ⓘ {p.explanation}
      </p>
    </div>
  );
}
