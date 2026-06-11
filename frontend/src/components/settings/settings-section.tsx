import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

interface SettingsSectionProps {
  title: string;
  description?: string;
  /** Right-aligned action (e.g. "Save changes" button). */
  action?: ReactNode;
  /** Subdued danger styling for destructive sections. */
  danger?: boolean;
  children: ReactNode;
  className?: string;
}

export function SettingsSection({
  title,
  description,
  action,
  danger,
  children,
  className,
}: SettingsSectionProps) {
  return (
    <section
      className={cn("pix-root pix-frame p-5 sm:p-6", className)}
      style={
        danger
          ? {
              background: "var(--pix-parch)",
              borderColor: "var(--pix-red)",
            }
          : undefined
      }
    >
      <header
        className={cn(
          "flex flex-wrap items-start justify-between gap-3",
          children ? "mb-5" : "",
        )}
      >
        <div className="min-w-0 flex-1">
          <h2
            style={{
              fontFamily: '"Pixelify Sans", sans-serif',
              fontSize: "16px",
              fontWeight: 700,
              color: danger ? "var(--pix-red)" : "var(--pix-gold-dark)",
              letterSpacing: "0.02em",
            }}
          >
            {title}
          </h2>
          {description && (
            <p
              style={{
                fontFamily: '"VT323", monospace',
                fontSize: "15px",
                color: "var(--pix-ink-soft)",
                marginTop: "2px",
              }}
            >
              {description}
            </p>
          )}
        </div>
        {action && <div className="shrink-0">{action}</div>}
      </header>
      {children}
    </section>
  );
}

interface SettingsRowProps {
  label: string;
  description?: string;
  /** Form/control on the right. */
  control: ReactNode;
  className?: string;
}

export function SettingsRow({ label, description, control, className }: SettingsRowProps) {
  return (
    <div
      className={cn("flex flex-wrap items-start justify-between gap-3 pt-4 first:pt-0", className)}
      style={{
        borderTop: "1px solid var(--pix-parch-line)",
      }}
    >
      <div className="min-w-0 flex-1">
        <p
          style={{
            fontFamily: '"Pixelify Sans", sans-serif',
            fontSize: "14px",
            fontWeight: 600,
            color: "var(--pix-ink)",
          }}
        >
          {label}
        </p>
        {description && (
          <p
            style={{
              fontFamily: '"VT323", monospace',
              fontSize: "14px",
              color: "var(--pix-ink-soft)",
              marginTop: "2px",
            }}
          >
            {description}
          </p>
        )}
      </div>
      <div className="shrink-0">{control}</div>
    </div>
  );
}
