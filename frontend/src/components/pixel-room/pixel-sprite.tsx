"use client";

/**
 * Clean-room box-shadow pixel sprite engine.
 *
 * A pixel map (string[]) is converted into a single CSS `box-shadow` value:
 * every non-empty cell becomes one shadow `${c*scale}px ${r*scale}px 0 0 color`.
 * A 1×scale div then "paints" the whole sprite via its box-shadow — no canvas.
 *
 * Characters are authored as cute, clearly-human little office workers on a
 * 16-wide × 22-tall grid: big head (~40%), 2 eyes + brows + mouth, a hair cap
 * with fringe, a shirt with a collar band + tie accent, two arms with hands,
 * two legs with a gap, and shoes. A 1px dark outline (legend `o`) wraps the
 * silhouette so it reads on any background.
 */

import { useMemo, type CSSProperties } from "react";

export type SpritePalette = Record<string, string | null>;

/**
 * Base palette. Char legend:
 *  .  transparent   o  outline (silhouette edge)
 *  K  hair          k  hair-shadow
 *  F  face          f  face-shadow      B  brow
 *  E  eyes          M  mouth
 *  W  collar (light) S  shirt           s  shirt-shadow
 *  T  tie / accent  G  glasses lens
 *  A  arm (skin)    H  hand (skin)
 *  P  pants         p  pants-shadow     O  shoes
 */
export const SPRITE_PALETTE: SpritePalette = {
  ".": null,
  o: "#241a12", // outline
  K: "#4a2f17", // hair
  k: "#33200f", // hair shadow
  F: "#f0c094", // face
  f: "#d99e6b", // face shadow
  B: "#7a4a23", // brow
  E: "#26303a", // eyes
  M: "#9c6b4a", // mouth
  W: "#f3ead2", // collar (light)
  S: "#4f8a4e", // shirt
  s: "#356b3a", // shirt shadow
  T: "#e7b53c", // tie / accent
  G: "#bfe6ff", // glasses lens
  A: "#f0c094", // arm (skin)
  H: "#e7b07f", // hand (skin)
  P: "#33271a", // pants
  p: "#241a10", // pants shadow
  O: "#1c130b", // shoes
};

/**
 * ── BODY MAPS ──────────────────────────────────────────────────────────────
 * 16 wide × 22 tall. Hair (K/k) is only the back/sides here; a hair OVERLAY
 * is composited on top to give each style its fringe & shape. Legs come in
 * two frames (stand / step) for a simple 2-frame walk cycle.
 */

// Standing body — legs together.
export const BODY_STAND: string[] = [
  "................",
  "................",
  ".....oooooo.....",
  "....okkkkkko....",
  "...okkkkkkkko...",
  "...oFFFFFFFFo...",
  "...oFFFFFFFFo...",
  "..oFBFFFFFFBFo..", // brows
  "..oFEFFFFFFEFo..", // eyes
  "..oFFFFFFFFFFo..",
  "..oFfFMMMMFfFo..", // mouth
  "..ooFFFFFFFFoo..",
  "...oWWSSSSWWo...", // collar
  "..oAsSSTTSSsAo..", // shoulders + tie
  ".oHASSSTTSSSAHo.", // arms + hands + tie
  ".oHASSSSSSSSAHo.",
  "..ooSSSSSSSSoo..",
  "...oPPPPPPPPo...",
  "...oPPoooPPPo...",
  "...oPPo.oPPo....",
  "...oOOo.oOOo....",
  "...ooo...ooo....",
];

// Walking body — legs apart (step frame). Same head/torso, different legs.
export const BODY_STEP: string[] = [
  "................",
  "................",
  ".....oooooo.....",
  "....okkkkkko....",
  "...okkkkkkkko...",
  "...oFFFFFFFFo...",
  "...oFFFFFFFFo...",
  "..oFBFFFFFFBFo..",
  "..oFEFFFFFFEFo..",
  "..oFFFFFFFFFFo..",
  "..oFfFMMMMFfFo..",
  "..ooFFFFFFFFoo..",
  "...oWWSSSSWWo...",
  "..oAsSSTTSSsAo..",
  ".oHASSSTTSSSAHo.",
  "..oASSSSSSSSAHo.",
  "..ooSSSSSSSSoo..",
  "...oPPPPPPPPo...",
  "..oPPPo.oPPPo...",
  ".oPPo....oPPo...",
  ".oOOo....oOOo...",
  ".ooo......ooo...",
];

/**
 * ── HAIR OVERLAY MAPS ────────────────────────────────────────────────────────
 * Composited on top of the body. Only paint hair cells (K/k); everything else
 * transparent. Rows align to the body grid above (head rows 2-11).
 */

const HAIR_SHORT: string[] = [
  "................",
  "................",
  ".....KKKKKK.....",
  "....KKKKKKKK....",
  "...KKKKKKKKKK...",
  "...KKkFFFFkKK...", // fringe over forehead
  "...KKFFFFFFKK...",
  "...K.FFFFFF.K...",
  "................",
];

const HAIR_LONG: string[] = [
  "................",
  "................",
  ".....KKKKKK.....",
  "....KKKKKKKK....",
  "...KKKKKKKKKK...",
  "..KKKkFFFFkKKK..",
  "..KKKFFFFFFKKK..",
  "..KKKFFFFFFKKK..",
  "..KK.FFFFFF.KK..",
  "..KK.FFFFFF.KK..",
  "..KK........KK..",
  "..KK........KK..",
];

const HAIR_BUN: string[] = [
  ".......KK.......", // top bun
  "......KKKK......",
  ".....KKKKKK.....",
  "....KKKKKKKK....",
  "...KKKKKKKKKK...",
  "...KKkFFFFkKK...",
  "...KKFFFFFFKK...",
  "...K.FFFFFF.K...",
  "................",
];

const HAIR_SPIKY: string[] = [
  "...K.K..K.K.K...", // spikes
  "...KKKKKKKKKK...",
  ".....KKKKKK.....",
  "....KKKKKKKK....",
  "...KKKKKKKKKK...",
  "...KkkFFFFkkK...",
  "...KKFFFFFFKK...",
  "...K.FFFFFF.K...",
  "................",
];

// "cap" = bald / very short — minimal hairline only.
const HAIR_CAP: string[] = [
  "................",
  "................",
  ".....KKKKKK.....",
  "....KKKKKKKK....",
  "...KKKKKKKKKK...",
  "...KkFFFFFFkK...",
  "....FFFFFFFF....",
  "....FFFFFFFF....",
  "................",
];

export type HairStyle = "short" | "long" | "bun" | "spiky" | "cap";

export const HAIR_OVERLAYS: Record<HairStyle, string[]> = {
  short: HAIR_SHORT,
  long: HAIR_LONG,
  bun: HAIR_BUN,
  spiky: HAIR_SPIKY,
  cap: HAIR_CAP,
};

/**
 * ── ACCESSORY OVERLAYS ───────────────────────────────────────────────────────
 * Glasses paint over the eye row. `none`/`tie` add nothing here (the tie is part
 * of the body map and recolored via palette T).
 */
const GLASSES_OVERLAY: string[] = [
  "................",
  "................",
  "................",
  "................",
  "................",
  "................",
  "................",
  "................",
  "..ooGGooooGGoo..", // glasses frame + lenses over eye row
  "................",
];

export type Accessory = "none" | "tie" | "glasses";

/** Compose layers: later non-transparent cells win. All maps share the grid. */
export function composeMaps(...layers: string[][]): string[] {
  const height = Math.max(...layers.map((l) => l.length));
  const width = Math.max(...layers.flatMap((l) => l.map((row) => row.length)));
  const out: string[] = [];
  for (let r = 0; r < height; r++) {
    let row = "";
    for (let c = 0; c < width; c++) {
      let ch = ".";
      for (const layer of layers) {
        const lch = layer[r]?.[c];
        if (lch && lch !== ".") ch = lch;
      }
      row += ch;
    }
    out.push(row);
  }
  return out;
}

/**
 * Build a full character map from a body frame + hair style (+ optional glasses).
 */
export function buildCharacterMap(
  body: string[],
  hair: HairStyle,
  accessory: Accessory = "none",
): string[] {
  const layers: string[][] = [body, HAIR_OVERLAYS[hair] ?? HAIR_SHORT];
  if (accessory === "glasses") layers.push(GLASSES_OVERLAY);
  return composeMaps(...layers);
}

// Back-compat aliases: previous code imported these two map names.
export const TRADER_MAP: string[] = buildCharacterMap(BODY_STAND, "short");
export const TRADER_MAP_LONG: string[] = buildCharacterMap(BODY_STAND, "long");

/** Merge overrides onto the base palette. */
export function mkPalette(overrides: SpritePalette): SpritePalette {
  return { ...SPRITE_PALETTE, ...overrides };
}

/** Build a single box-shadow string painting every non-transparent pixel. */
function buildShadows(map: string[], scale: number, palette: SpritePalette): string {
  const parts: string[] = [];
  for (let r = 0; r < map.length; r++) {
    const row = map[r]!;
    for (let c = 0; c < row.length; c++) {
      const ch = row[c]!;
      const color = palette[ch];
      if (!color) continue;
      parts.push(`${c * scale}px ${r * scale}px 0 0 ${color}`);
    }
  }
  return parts.join(",");
}

export interface PixelSpriteProps {
  map: string[];
  scale?: number;
  palette?: SpritePalette;
  flip?: boolean;
  className?: string;
}

export function PixelSprite({
  map,
  scale = 4,
  palette = SPRITE_PALETTE,
  flip = false,
  className = "",
}: PixelSpriteProps) {
  const cols = map.reduce((m, row) => Math.max(m, row.length), 0);
  const rows = map.length;
  const shadow = useMemo(() => buildShadows(map, scale, palette), [map, scale, palette]);

  const wrapStyle: CSSProperties = {
    position: "relative",
    width: cols * scale,
    height: rows * scale,
    transform: flip ? "scaleX(-1)" : undefined,
    imageRendering: "pixelated",
  };
  const pxStyle: CSSProperties = {
    position: "absolute",
    left: 0,
    top: 0,
    width: scale,
    height: scale,
    boxShadow: shadow,
  };

  return (
    <div className={`pdr-sprite ${className}`.trim()} style={wrapStyle}>
      <div className="pdr-px" style={pxStyle} />
    </div>
  );
}

// ── Agent ─────────────────────────────────────────────────────────────────────

export interface SpriteAgent {
  id: string;
  name: string;
  tint: string;
  map: string[];
  palette: SpritePalette;
  pos: { x: number; y: number }; // % within the room
  bubble?: string | null;
  walking?: boolean;
  flip?: boolean;
  status?: "idle" | "running" | "done" | "error";
  /** Optional alternate frame used for the walk step (legs apart). */
  walkMap?: string[];
}

export interface AgentProps {
  agent: SpriteAgent;
  scale?: number;
  showName?: boolean;
  z?: number;
  animate?: boolean;
}

export function Agent({ agent, scale = 3, showName = true, z, animate = true }: AgentProps) {
  const walking = animate && agent.walking;
  const running = agent.status === "running";

  return (
    <div
      className="pdr-agent"
      style={{ left: `${agent.pos.x}%`, top: `${agent.pos.y}%`, zIndex: z }}
    >
      {agent.bubble ? <div className="pdr-bubble">{agent.bubble}</div> : null}
      {running ? <div className="pdr-ring" style={{ borderColor: agent.tint }} /> : null}
      <div className="pdr-shadow" />
      <div className={`pdr-bobber${walking ? " pdr-walking" : ""}`}>
        {/* When walking and a step frame exists, swap frames via CSS visibility. */}
        {walking && agent.walkMap ? (
          <div className="pdr-walkframes">
            <div className="pdr-frame-a">
              <PixelSprite map={agent.map} scale={scale} palette={agent.palette} flip={agent.flip} />
            </div>
            <div className="pdr-frame-b">
              <PixelSprite map={agent.walkMap} scale={scale} palette={agent.palette} flip={agent.flip} />
            </div>
          </div>
        ) : (
          <PixelSprite map={agent.map} scale={scale} palette={agent.palette} flip={agent.flip} />
        )}
      </div>
      {showName ? (
        <div className="pdr-nametag" style={{ borderColor: agent.tint }}>
          {agent.name}
        </div>
      ) : null}
    </div>
  );
}

// ── MiniFace (head-only avatar for the sidebar / roster) ────────────────────────

export interface MiniFaceProps {
  palette?: SpritePalette;
  map?: string[];
  scale?: number;
}

export function MiniFace({ palette = SPRITE_PALETTE, map = TRADER_MAP, scale = 4 }: MiniFaceProps) {
  // Head occupies roughly the top half of the 22-row sprite.
  const head = useMemo(() => map.slice(2, 12), [map]);
  return <PixelSprite map={head} scale={scale} palette={palette} />;
}
