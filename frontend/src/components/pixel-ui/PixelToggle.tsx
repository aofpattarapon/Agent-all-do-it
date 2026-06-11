interface PixelToggleProps {
  on: boolean;
  onChange: (next: boolean) => void;
  "aria-label"?: string;
}

export function PixelToggle({ on, onChange, ...rest }: PixelToggleProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      className={"pix-toggle" + (on ? " pix-on" : "")}
      onClick={() => onChange(!on)}
      {...rest}
    >
      <span className="pix-knob" />
    </button>
  );
}
