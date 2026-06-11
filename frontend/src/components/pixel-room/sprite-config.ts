/**
 * Maps our existing SpriteId / agent avatars onto a box-shadow sprite
 * (a pixel map + palette + a UI tint color). Deterministic per type so a
 * given agent always reads the same colors.
 */

import { CHARACTERS } from "@/components/pixel-room/characters";
import {
  BODY_STAND,
  BODY_STEP,
  buildCharacterMap,
  mkPalette,
  type Accessory,
  type HairStyle,
} from "@/components/pixel-room/pixel-sprite";
import type { SpritePalette } from "@/components/pixel-room/pixel-sprite";
import { SPRITE_IDS, type SpriteId } from "@/components/pixel/sprites";

export interface SpriteForAvatar {
  map: string[];
  /** Alternate "legs apart" frame for the walk cycle. */
  walkMap: string[];
  palette: SpritePalette;
  tint: string;
}

/** A character config that may be stored on an agent's tools_config.character. */
export interface CharacterConfig {
  baseId?: string;
  skinTone?: string;
  hairColor?: string;
  shirtColor?: string;
  pantsColor?: string;
  /** New optional cosmetic fields. */
  hairStyle?: HairStyle;
  accessory?: Accessory;
  accentColor?: string;
}

// Default hair style per sprite id (purely cosmetic variety).
const HAIR_BY_ID: Partial<Record<SpriteId, HairStyle>> = {
  coder: "short",
  analyst: "long",
  designer: "bun",
  manager: "short",
  qa_bot: "spiky",
  devops: "cap",
  wizard: "long",
  robot: "cap",
  ninja: "cap",
  scientist: "long",
  architect: "short",
  writer: "long",
  detective: "short",
  captain: "cap",
  ghost: "long",
};

// Default accessory per sprite id.
const ACCESSORY_BY_ID: Partial<Record<SpriteId, Accessory>> = {
  analyst: "tie",
  manager: "tie",
  scientist: "glasses",
  writer: "glasses",
  detective: "glasses",
  captain: "tie",
};

function paletteFromColors(colors: {
  skinTone: string;
  hairColor: string;
  shirtColor: string;
  pantsColor: string;
  shirtAccent: string;
  shoeColor: string;
}): SpritePalette {
  return mkPalette({
    F: colors.skinTone,
    f: shade(colors.skinTone, -0.18),
    A: colors.skinTone,
    H: shade(colors.skinTone, -0.1),
    B: shade(colors.hairColor, 0.1),
    K: colors.hairColor,
    k: shade(colors.hairColor, -0.25),
    S: colors.shirtColor,
    s: shade(colors.shirtColor, -0.22),
    W: shade(colors.shirtColor, 0.42),
    T: colors.shirtAccent,
    P: colors.pantsColor,
    p: shade(colors.pantsColor, -0.28),
    O: colors.shoeColor,
  });
}

/** Darken (amount < 0) or lighten (amount > 0) a hex color. */
function shade(hex: string, amount: number): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return hex;
  const num = parseInt(m[1]!, 16);
  const adj = (c: number) =>
    Math.max(0, Math.min(255, Math.round(c + (amount < 0 ? c : 255 - c) * amount)));
  const r = adj((num >> 16) & 0xff);
  const g = adj((num >> 8) & 0xff);
  const b = adj(num & 0xff);
  return `#${((1 << 24) | (r << 16) | (g << 8) | b).toString(16).slice(1)}`;
}

/** Resolve an avatar string to a known SpriteId (deterministic fallback by index). */
function resolveSpriteId(avatar: string, index: number): SpriteId {
  const direct = SPRITE_IDS.find((id) => id === avatar);
  if (direct) return direct;
  return SPRITE_IDS[index % SPRITE_IDS.length] ?? "robot";
}

const HAIR_STYLES: ReadonlySet<string> = new Set<HairStyle>([
  "short",
  "long",
  "bun",
  "spiky",
  "cap",
]);
const ACCESSORIES: ReadonlySet<string> = new Set<Accessory>(["none", "tie", "glasses"]);

/**
 * Resolve an avatar (+ optional stored character config) into a renderable sprite.
 * When a CharacterConfig is supplied its colors/styles win.
 */
export function getSpriteForAvatar(
  avatar: string,
  index: number,
  character?: CharacterConfig | null,
): SpriteForAvatar {
  // A stored baseId on the config wins over the agent's avatar field.
  const baseAvatar =
    character?.baseId && SPRITE_IDS.includes(character.baseId as SpriteId)
      ? character.baseId
      : avatar;
  const id = resolveSpriteId(baseAvatar, index);
  const def = CHARACTERS[id];

  const hairStyle: HairStyle =
    character?.hairStyle && HAIR_STYLES.has(character.hairStyle)
      ? character.hairStyle
      : HAIR_BY_ID[id] ?? "short";
  const accessory: Accessory =
    character?.accessory && ACCESSORIES.has(character.accessory)
      ? character.accessory
      : ACCESSORY_BY_ID[id] ?? "none";

  const colors = {
    skinTone: character?.skinTone ?? def.skinTone,
    hairColor: character?.hairColor ?? def.hairColor,
    shirtColor: character?.shirtColor ?? def.shirtColor,
    pantsColor: character?.pantsColor ?? def.pantsColor,
    shirtAccent: character?.accentColor ?? def.shirtAccent,
    shoeColor: def.shoeColor,
  };

  return {
    map: buildCharacterMap(BODY_STAND, hairStyle, accessory),
    walkMap: buildCharacterMap(BODY_STEP, hairStyle, accessory),
    palette: paletteFromColors(colors),
    tint: character?.accentColor ?? def.accentColor,
  };
}

// ── LPC (Liberated Pixel Cup) realistic sprite mapping ───────────────────────

/**
 * Path to an LPC layer file. Mirrors the curated set downloaded into
 * `public/sprites/lpc/` (served at `/sprites/lpc/...`).
 */
export interface LpcLook {
  body: string;
  hair?: string;
  shirt?: string;
  pants?: string;
  shoes?: string;
}

/** A loose character-config shape (CharacterConfig from either module). */
export interface CharacterConfigLike {
  baseId?: string;
  skinTone?: string;
  hairColor?: string;
  shirtColor?: string;
  pantsColor?: string;
}

const LPC = (file: string): string => `/sprites/lpc/${file}`;

// The set we actually downloaded. Anything chosen must resolve into one of
// these or fall back to a guaranteed-present default.
const LPC_FILES = {
  bodies: [
    "body_light.png",
    "body_dark.png",
    "body_tan.png",
    "body_female_light.png",
    "body_female_dark.png",
  ],
  hairs: [
    "hair_black.png",
    "hair_brown.png",
    "hair_blonde.png",
    "hair_female_brown.png",
    "hair_female_blonde.png",
  ],
  shirts: ["shirt_white.png", "shirt_teal.png", "shirt_maroon.png", "shirt_brown.png"],
  pants: ["pants_teal.png", "pants_red.png", "pants_white.png"],
  shoes: ["shoes_black.png", "shoes_brown.png"],
} as const;

const LPC_DEFAULT: Required<LpcLook> = {
  body: LPC("body_light.png"),
  hair: LPC("hair_brown.png"),
  shirt: LPC("shirt_white.png"),
  pants: LPC("pants_teal.png"),
  shoes: LPC("shoes_black.png"),
};

/** Ensure a chosen file exists in the downloaded set; else fall back. */
function pick(file: string, set: readonly string[], fallback: string): string {
  return LPC(set.includes(file) ? file : fallback);
}

function hexToRgb(hex: string): [number, number, number] | null {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return null;
  const n = parseInt(m[1]!, 16);
  return [(n >> 16) & 0xff, (n >> 8) & 0xff, n & 0xff];
}

function luma(hex: string): number {
  const rgb = hexToRgb(hex);
  if (!rgb) return 0.5;
  return (0.299 * rgb[0] + 0.587 * rgb[1] + 0.714 * rgb[2]) / 255;
}

/** Nearest body file from a skin-tone hex (by brightness). */
function nearestBody(skinTone: string | undefined, female: boolean): string {
  const l = skinTone ? luma(skinTone) : 0.6;
  if (female) return l < 0.45 ? "body_female_dark.png" : "body_female_light.png";
  if (l < 0.4) return "body_dark.png";
  if (l < 0.62) return "body_tan.png";
  return "body_light.png";
}

/** Nearest hair file from a hair-color hex. */
function nearestHair(hairColor: string | undefined, female: boolean): string {
  const l = hairColor ? luma(hairColor) : 0.3;
  if (female) return l > 0.6 ? "hair_female_blonde.png" : "hair_female_brown.png";
  if (l > 0.6) return "hair_blonde.png";
  if (l > 0.32) return "hair_brown.png";
  return "hair_black.png";
}

/** Nearest shirt file from a shirt-color hex (by hue family + brightness). */
function nearestShirt(shirtColor: string | undefined): string {
  const rgb = shirtColor ? hexToRgb(shirtColor) : null;
  if (!rgb) return "shirt_white.png";
  const [r, g, b] = rgb;
  if (r > 200 && g > 200 && b > 200) return "shirt_white.png";
  // reddish/maroon
  if (r > g && r > b && r - Math.max(g, b) > 30) return "shirt_maroon.png";
  // brownish (r & g elevated, low b)
  if (r > 90 && g > 50 && b < 90 && r >= g) return "shirt_brown.png";
  // teal/blue/green-ish
  if (b > r || g > r) return "shirt_teal.png";
  return "shirt_white.png";
}

/** Nearest pants file from a pants-color hex. */
function nearestPants(pantsColor: string | undefined): string {
  const rgb = pantsColor ? hexToRgb(pantsColor) : null;
  if (!rgb) return "pants_teal.png";
  const [r, g, b] = rgb;
  if (r > 190 && g > 190 && b > 190) return "pants_white.png";
  if (r > g && r > b && r - Math.max(g, b) > 30) return "pants_red.png";
  return "pants_teal.png";
}

// Distinct default looks per SpriteId so each character reads differently even
// without a stored CharacterConfig. Files always live in the downloaded set.
const LPC_BY_ID: Partial<Record<SpriteId, LpcLook>> = {
  coder: {
    body: LPC("body_light.png"),
    hair: LPC("hair_black.png"),
    shirt: LPC("shirt_teal.png"),
    pants: LPC("pants_teal.png"),
    shoes: LPC("shoes_black.png"),
  },
  analyst: {
    body: LPC("body_tan.png"),
    hair: LPC("hair_brown.png"),
    shirt: LPC("shirt_white.png"),
    pants: LPC("pants_teal.png"),
    shoes: LPC("shoes_brown.png"),
  },
  designer: {
    body: LPC("body_female_light.png"),
    hair: LPC("hair_female_brown.png"),
    shirt: LPC("shirt_maroon.png"),
    pants: LPC("pants_white.png"),
    shoes: LPC("shoes_black.png"),
  },
  manager: {
    body: LPC("body_light.png"),
    hair: LPC("hair_black.png"),
    shirt: LPC("shirt_white.png"),
    pants: LPC("pants_teal.png"),
    shoes: LPC("shoes_black.png"),
  },
  qa_bot: {
    body: LPC("body_light.png"),
    hair: LPC("hair_black.png"),
    shirt: LPC("shirt_teal.png"),
    pants: LPC("pants_white.png"),
    shoes: LPC("shoes_black.png"),
  },
  devops: {
    body: LPC("body_dark.png"),
    hair: LPC("hair_black.png"),
    shirt: LPC("shirt_brown.png"),
    pants: LPC("pants_teal.png"),
    shoes: LPC("shoes_brown.png"),
  },
  wizard: {
    body: LPC("body_light.png"),
    hair: LPC("hair_blonde.png"),
    shirt: LPC("shirt_maroon.png"),
    pants: LPC("pants_red.png"),
    shoes: LPC("shoes_brown.png"),
  },
  robot: {
    body: LPC("body_tan.png"),
    hair: LPC("hair_black.png"),
    shirt: LPC("shirt_teal.png"),
    pants: LPC("pants_teal.png"),
    shoes: LPC("shoes_black.png"),
  },
  ninja: {
    body: LPC("body_light.png"),
    hair: LPC("hair_black.png"),
    shirt: LPC("shirt_maroon.png"),
    pants: LPC("pants_teal.png"),
    shoes: LPC("shoes_black.png"),
  },
  scientist: {
    body: LPC("body_female_light.png"),
    hair: LPC("hair_female_blonde.png"),
    shirt: LPC("shirt_white.png"),
    pants: LPC("pants_white.png"),
    shoes: LPC("shoes_black.png"),
  },
  architect: {
    body: LPC("body_tan.png"),
    hair: LPC("hair_brown.png"),
    shirt: LPC("shirt_brown.png"),
    pants: LPC("pants_red.png"),
    shoes: LPC("shoes_brown.png"),
  },
  writer: {
    body: LPC("body_light.png"),
    hair: LPC("hair_brown.png"),
    shirt: LPC("shirt_teal.png"),
    pants: LPC("pants_red.png"),
    shoes: LPC("shoes_brown.png"),
  },
  detective: {
    body: LPC("body_dark.png"),
    hair: LPC("hair_black.png"),
    shirt: LPC("shirt_brown.png"),
    pants: LPC("pants_teal.png"),
    shoes: LPC("shoes_black.png"),
  },
  captain: {
    body: LPC("body_light.png"),
    hair: LPC("hair_black.png"),
    shirt: LPC("shirt_teal.png"),
    pants: LPC("pants_white.png"),
    shoes: LPC("shoes_black.png"),
  },
  ghost: {
    body: LPC("body_female_light.png"),
    hair: LPC("hair_female_blonde.png"),
    shirt: LPC("shirt_white.png"),
    pants: LPC("pants_white.png"),
    shoes: LPC("shoes_black.png"),
  },
};

const FEMALE_IDS: ReadonlySet<SpriteId> = new Set<SpriteId>(["designer", "scientist", "ghost"]);

/**
 * Deterministic mapping from a SpriteId / CharacterConfig to a curated LPC
 * layer combo. When a CharacterConfig with colors is supplied, those map to the
 * nearest available layer; otherwise a distinct per-SpriteId default is used.
 * Always resolves to files present in the downloaded set.
 */
export function getLpcLook(
  avatar: string,
  index: number,
  character?: CharacterConfigLike | null,
): LpcLook {
  const baseAvatar =
    character?.baseId && SPRITE_IDS.includes(character.baseId as SpriteId)
      ? character.baseId
      : avatar;
  const id = resolveSpriteId(baseAvatar, index);
  const base = LPC_BY_ID[id] ?? LPC_DEFAULT;
  const female = FEMALE_IDS.has(id);

  // No explicit color config → use the curated per-id look as-is.
  const hasColors =
    character &&
    (character.skinTone || character.hairColor || character.shirtColor || character.pantsColor);
  if (!hasColors) return base;

  return {
    body: pick(nearestBody(character.skinTone, female), LPC_FILES.bodies, "body_light.png"),
    hair: pick(nearestHair(character.hairColor, female), LPC_FILES.hairs, "hair_brown.png"),
    shirt: pick(nearestShirt(character.shirtColor), LPC_FILES.shirts, "shirt_white.png"),
    pants: pick(nearestPants(character.pantsColor), LPC_FILES.pants, "pants_teal.png"),
    shoes: base.shoes ?? LPC_DEFAULT.shoes,
  };
}

/** Safely parse a stored character config (JSON string or object). */
export function parseCharacterConfig(raw: unknown): CharacterConfig | null {
  if (!raw) return null;
  let obj: unknown = raw;
  if (typeof raw === "string") {
    try {
      obj = JSON.parse(raw);
    } catch {
      return null;
    }
  }
  if (typeof obj !== "object" || obj === null) return null;
  const c = obj as Record<string, unknown>;
  const pick = (k: string): string | undefined =>
    typeof c[k] === "string" ? (c[k] as string) : undefined;
  const hs = pick("hairStyle");
  const ac = pick("accessory");
  return {
    baseId: pick("baseId"),
    skinTone: pick("skinTone"),
    hairColor: pick("hairColor"),
    shirtColor: pick("shirtColor"),
    pantsColor: pick("pantsColor"),
    hairStyle: hs && HAIR_STYLES.has(hs) ? (hs as HairStyle) : undefined,
    accessory: ac && ACCESSORIES.has(ac) ? (ac as Accessory) : undefined,
    accentColor: pick("accentColor"),
  };
}
