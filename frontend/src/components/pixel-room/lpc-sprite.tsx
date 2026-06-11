"use client";

/**
 * LpcSprite — composites Universal LPC Spritesheet layers onto a canvas and
 * animates the walk cycle. Each layer PNG is an 832×1344 sheet of 64×64 frames
 * (13 cols × 21 rows). The walk animation lives on rows 8 (up), 9 (left),
 * 10 (down), 11 (right); col 0 = idle/standing, cols 1..8 = walk cycle.
 *
 * Layers composite by simple overlay in z-order: body → pants → shoes →
 * shirt → hair.
 */

import { useEffect, useReducer, useRef } from "react";

// ── Types ──────────────────────────────────────────────────────────────────

export interface LpcLook {
  /** Each value is a path like "/sprites/lpc/<file>.png". */
  body: string;
  hair?: string;
  shirt?: string;
  pants?: string;
  shoes?: string;
}

export type LpcDirection = "up" | "down" | "left" | "right";

export interface LpcSpriteProps {
  look: LpcLook;
  direction?: LpcDirection;
  /** Cycle the walk frames vs. holding the idle frame (col 0). */
  walking?: boolean;
  /** Render scale (e.g. 2 → 128px). Each frame is 64×64. */
  scale?: number;
  /** Walk animation frames per second (default 6 for smoother cadence). */
  fps?: number;
}

// ── Frame geometry ───────────────────────────────────────────────────────────

const FRAME = 64;
const ROW_BY_DIRECTION: Record<LpcDirection, number> = {
  up: 8,
  left: 9,
  down: 10,
  right: 11,
};
const WALK_FRAMES = 8; // cols 1..8

// Layers in z-order (bottom first).
const LAYER_ORDER: (keyof LpcLook)[] = ["body", "pants", "shoes", "shirt", "hair"];

// ── Image cache (module-level, dedupes in-flight loads) ──────────────────────

type LoadState = { img: HTMLImageElement; ready: boolean };
const cache = new Map<string, Promise<HTMLImageElement>>();
const ready = new Map<string, LoadState>();

function loadImage(url: string): Promise<HTMLImageElement> {
  const existing = cache.get(url);
  if (existing) return existing;
  const p = new Promise<HTMLImageElement>((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      ready.set(url, { img, ready: true });
      resolve(img);
    };
    img.onerror = (e) => {
      cache.delete(url);
      reject(e);
    };
    img.src = url;
  });
  cache.set(url, p);
  return p;
}

/** Preload all layer images for a look (fire-and-forget safe). */
export function preloadLook(look: LpcLook): void {
  for (const key of LAYER_ORDER) {
    const url = look[key];
    if (url) void loadImage(url).catch(() => undefined);
  }
}

// ── Component ────────────────────────────────────────────────────────────────

export function LpcSprite({
  look,
  direction = "down",
  walking = false,
  scale = 2,
  fps = 6,
}: LpcSpriteProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  // Serialize the look so the effect only re-runs when the actual urls change.
  const lookKey = LAYER_ORDER.map((k) => look[k] ?? "").join("|");

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let cancelled = false;
    let raf = 0;
    let lastDraw = 0;
    let tick = 0;

    const urls = LAYER_ORDER.map((k) => look[k]).filter(
      (u): u is string => typeof u === "string" && u.length > 0,
    );

    const draw = () => {
      if (cancelled) return;
      const row = ROW_BY_DIRECTION[direction];
      const col = walking ? 1 + (tick % WALK_FRAMES) : 0;
      ctx.clearRect(0, 0, FRAME, FRAME);
      for (const key of LAYER_ORDER) {
        const url = look[key];
        if (!url) continue;
        const state = ready.get(url);
        if (!state?.ready) continue;
        try {
          ctx.drawImage(
            state.img,
            col * FRAME,
            row * FRAME,
            FRAME,
            FRAME,
            0,
            0,
            FRAME,
            FRAME,
          );
        } catch {
          // Image not yet decodable; skip this layer this frame.
        }
      }
    };

    const interval = 1000 / Math.max(1, fps);
    const loop = (now: number) => {
      if (cancelled) return;
      if (now - lastDraw >= interval) {
        lastDraw = now;
        tick += 1;
        draw();
      }
      raf = requestAnimationFrame(loop);
    };

    // Load every layer, then draw. If walking, start the rAF cycle; otherwise
    // just draw a single idle frame.
    Promise.allSettled(urls.map((u) => loadImage(u))).then(() => {
      if (cancelled) return;
      draw();
      if (walking) {
        raf = requestAnimationFrame(loop);
      }
    });

    return () => {
      cancelled = true;
      if (raf) cancelAnimationFrame(raf);
    };
  }, [lookKey, direction, walking, fps, look]);

  const px = FRAME * scale;
  return (
    <div style={{ display: "inline-block", transition: "transform 0.1s ease" }}>
      <canvas
        ref={canvasRef}
        width={FRAME}
        height={FRAME}
        style={{
          width: px,
          height: px,
          imageRendering: "pixelated",
          display: "block",
        }}
      />
    </div>
  );
}

// ── Availability probe ───────────────────────────────────────────────────────

const PROBE_URL = "/sprites/lpc/body_light.png";
let probeState: "unknown" | "ok" | "fail" = "unknown";
const probeListeners = new Set<() => void>();

function runProbe(): void {
  if (probeState !== "unknown") return;
  if (typeof window === "undefined") return;
  const img = new Image();
  img.onload = () => {
    probeState = "ok";
    probeListeners.forEach((l) => l());
  };
  img.onerror = () => {
    probeState = "fail";
    probeListeners.forEach((l) => l());
  };
  img.src = PROBE_URL;
}

/**
 * Resolves to `true` once the probe image loads (so the room can decide
 * whether to render LPC sprites or fall back to box-shadow sprites). Returns
 * `false` until then; never throws.
 */
export function useLpcAvailable(): boolean {
  const [, force] = useReducer((n: number) => n + 1, 0);
  useEffect(() => {
    if (probeState !== "unknown") return;
    const listener = () => force();
    probeListeners.add(listener);
    runProbe();
    return () => {
      probeListeners.delete(listener);
    };
  }, []);
  return probeState === "ok";
}
