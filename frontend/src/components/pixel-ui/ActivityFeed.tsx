import type { ReactNode } from "react";

export interface ActivityItem {
  id: string;
  ic: ReactNode;
  text: string;
  who?: string;
  tint?: string;
  kind?: "up" | "down" | "plain";
  time: string;
}

interface ActivityFeedProps {
  items: ActivityItem[];
  emptyText?: string;
}

export function ActivityFeed({ items, emptyText = "No activity yet." }: ActivityFeedProps) {
  return (
    <div className="pix-notif-list">
      {items.length === 0 && <div className="pix-mono pix-muted">{emptyText}</div>}
      {items.map((n) => (
        <div key={n.id} className={"pix-notif pix-" + (n.kind ?? "plain")}>
          <span className="pix-ic">{n.ic}</span>
          <div>
            <div className="pix-tx">{n.text}</div>
            <div className="pix-tm">
              {n.who && (
                <span className="pix-who" style={n.tint ? { color: n.tint } : undefined}>
                  {n.who}
                </span>
              )}
              {n.who && " · "}
              {n.time}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
