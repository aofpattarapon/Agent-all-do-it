export const CRON_PRESETS = [
  { label: "Every minute",          value: "* * * * *" },
  { label: "Every 5 minutes",       value: "*/5 * * * *" },
  { label: "Every 15 minutes",      value: "*/15 * * * *" },
  { label: "Every 30 minutes",      value: "*/30 * * * *" },
  { label: "Every hour",            value: "0 * * * *" },
  { label: "Every day at midnight", value: "0 0 * * *" },
  { label: "Every day at 9 AM",     value: "0 9 * * *" },
  { label: "Every Monday 9 AM",     value: "0 9 * * 1" },
  { label: "First day of month",    value: "0 0 1 * *" },
] as const;

export const COMMON_TIMEZONES = [
  "UTC", "Asia/Bangkok", "Asia/Tokyo", "Asia/Singapore",
  "America/New_York", "America/Los_Angeles", "Europe/London", "Europe/Paris",
];

/** Very simple human-readable cron description (not exhaustive). */
export function describeCron(expr: string): string {
  const preset = CRON_PRESETS.find(p => p.value === expr);
  if (preset) return preset.label;
  const parts = expr.trim().split(/\s+/);
  if (parts.length !== 5) return expr;
  const [min, hour, dom, , dow] = parts;
  if (min === "*" && hour === "*") return "Every minute";
  if (min?.startsWith("*/")) return `Every ${min.slice(2)} minutes`;
  if (dom === "*" && dow === "*") {
    if (hour === "*") return `Every hour at :${min?.padStart(2, "0")}`;
    return `Daily at ${hour?.padStart(2, "0")}:${min?.padStart(2, "0")}`;
  }
  return expr;
}
