"use client";

import { SPRITES, SPRITE_IDS, type SpriteId } from "./sprites";
import { PixelAvatar } from "./pixel-avatar";
import { cn } from "@/lib/utils";

interface SpritePickerProps {
  value: SpriteId;
  onChange: (id: SpriteId) => void;
  /** Columns in the grid — default 5 */
  cols?: number;
}

/**
 * Grid picker for pixel-art agent sprites.
 * Shows a 5-column grid of sprites; selected one has a highlighted border.
 */
export function SpritePicker({ value, onChange, cols = 5 }: SpritePickerProps) {
  return (
    <div className="space-y-2">
      <p className="text-sm font-medium">Pixel Avatar</p>
      <div
        className="grid gap-1.5 rounded-lg border border-border/40 bg-muted/20 p-2"
        style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}
      >
        {SPRITE_IDS.map((id) => {
          const sprite = SPRITES[id];
          const selected = value === id;
          return (
            <button
              key={id}
              type="button"
              title={sprite.label}
              onClick={() => onChange(id)}
              className={cn(
                "flex flex-col items-center gap-0.5 rounded-lg border-2 p-1.5 transition-all",
                selected
                  ? "border-primary bg-primary/10 shadow-md"
                  : "border-transparent hover:border-border hover:bg-muted/40",
              )}
            >
              <PixelAvatar spriteId={id} size={40} active={selected} />
              <span className="text-[9px] text-muted-foreground font-mono leading-none">
                {sprite.label}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
