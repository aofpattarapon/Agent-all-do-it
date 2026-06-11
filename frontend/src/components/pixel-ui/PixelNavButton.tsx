import type { ReactNode } from "react";

interface PixelNavButtonProps {
  icon: ReactNode;
  label: string;
  active?: boolean;
  badge?: number;
  onClick?: () => void;
}

export function PixelNavButton({ icon, label, active, badge, onClick }: PixelNavButtonProps) {
  return (
    <button type="button" className={"pix-nav-btn" + (active ? " pix-active" : "")} onClick={onClick}>
      <span className="pix-ico">{icon}</span>
      {label}
      {badge != null && badge > 0 && <span className="pix-badge">{badge}</span>}
    </button>
  );
}
