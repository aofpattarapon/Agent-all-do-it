import type { ReactNode } from "react";
import { PixelFrame } from "./PixelFrame";
import { Sparkline } from "./Sparkline";

interface StatCardProps {
  label: string;
  value: ReactNode;
  icon?: ReactNode;
  sub?: ReactNode;
  trend?: "up" | "down";
  spark?: number[];
  onClick?: () => void;
}

export function StatCard({ label, value, icon, sub, trend, spark, onClick }: StatCardProps) {
  const trendCls = trend === "up" ? " pix-up" : trend === "down" ? " pix-down" : "";
  return (
    <PixelFrame
      className={"pix-statcard" + (onClick ? " pix-clickable" : "")}
      onClick={onClick}
      role={onClick ? "button" : undefined}
    >
      <div className="pix-sc-head">
        <span className="pix-sc-label">{label}</span>
        {icon && <span className="pix-sc-ico">{icon}</span>}
      </div>
      <div className={"pix-sc-value" + trendCls}>{value}</div>
      {sub && <div className="pix-sc-sub">{sub}</div>}
      {spark && spark.length > 1 && <Sparkline data={spark} />}
    </PixelFrame>
  );
}
