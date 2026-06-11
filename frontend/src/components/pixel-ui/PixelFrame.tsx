import type { HTMLAttributes, ReactNode } from "react";

type FrameVariant = "parchment" | "wood" | "green" | "screen";

interface PixelFrameProps extends HTMLAttributes<HTMLDivElement> {
  variant?: FrameVariant;
  tight?: boolean;
  children?: ReactNode;
}

const variantClass: Record<FrameVariant, string> = {
  parchment: "",
  wood: "pix-wood",
  green: "pix-green",
  screen: "pix-screen",
};

export function PixelFrame({ variant = "parchment", tight, className, children, ...rest }: PixelFrameProps) {
  const classes = ["pix-frame", variantClass[variant], tight ? "pix-tight" : "", className ?? ""]
    .filter(Boolean)
    .join(" ");
  return (
    <div className={classes} {...rest}>
      {children}
    </div>
  );
}
