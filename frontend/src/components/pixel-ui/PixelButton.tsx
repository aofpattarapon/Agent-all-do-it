import type { ButtonHTMLAttributes, ReactNode } from "react";

type ButtonVariant = "default" | "gold" | "green" | "red";

interface PixelButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  children?: ReactNode;
}

const variantClass: Record<ButtonVariant, string> = {
  default: "",
  gold: "pix-gold",
  green: "pix-green",
  red: "pix-danger",
};

export function PixelButton({ variant = "default", className, children, ...rest }: PixelButtonProps) {
  const classes = ["pix-btn", variantClass[variant], className ?? ""].filter(Boolean).join(" ");
  return (
    <button type="button" className={classes} {...rest}>
      {children}
    </button>
  );
}
