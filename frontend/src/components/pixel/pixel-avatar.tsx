"use client";

import { getSpritePixels, SPRITES, type SpriteId } from "./sprites";

interface PixelAvatarProps {
  spriteId: SpriteId;
  /** Rendered size in px (square). Pixel grid is 16×16. */
  size?: number;
  /** Optional animation class e.g. "animate-bounce" */
  className?: string;
  /** Show glow ring when active */
  active?: boolean;
  /** Color for glow ring — defaults to blue */
  glowColor?: string;
}

/**
 * Renders a 16×16 pixel-art sprite as an inline SVG.
 * Each "pixel" is a <rect> element — no external assets needed.
 */
export function PixelAvatar({
  spriteId,
  size = 64,
  className = "",
  active = false,
  glowColor = "#63b3ed",
}: PixelAvatarProps) {
  const pixels = getSpritePixels(spriteId);
  const px = size / 16; // size of one "pixel"

  return (
    <div
      className={`inline-block shrink-0 ${className}`}
      style={{
        width: size,
        height: size,
        imageRendering: "pixelated",
        filter: active
          ? `drop-shadow(0 0 6px ${glowColor}) drop-shadow(0 0 12px ${glowColor}60)`
          : undefined,
      }}
    >
      <svg
        width={size}
        height={size}
        viewBox="0 0 16 16"
        xmlns="http://www.w3.org/2000/svg"
        style={{ imageRendering: "pixelated" }}
        shapeRendering="crispEdges"
      >
        {pixels.map(({ x, y, color }) => (
          <rect
            key={`${x}-${y}`}
            x={x}
            y={y}
            width={1}
            height={1}
            fill={color}
          />
        ))}
      </svg>
    </div>
  );
}

/** Small inline label chip with pixel avatar */
export function PixelAvatarChip({
  spriteId,
  name,
  size = 24,
}: {
  spriteId: SpriteId;
  name: string;
  size?: number;
}) {
  const label = SPRITES[spriteId]?.label ?? spriteId;
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-muted/40 border border-border/40 px-2 py-0.5">
      <PixelAvatar spriteId={spriteId} size={size} />
      <span className="text-xs font-medium">{name || label}</span>
    </span>
  );
}
