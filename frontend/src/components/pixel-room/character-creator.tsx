"use client";

/**
 * Character creator — LPC-only.
 * Shows a live LpcSprite preview with walk/idle toggle, 4 color pickers
 * (skin tone, hair color, shirt, pants), and 4 quick presets.
 */

import { useMemo, useState } from "react";
import { getLpcLook } from "./sprite-config";
import { LpcSprite } from "./lpc-sprite";
import type { SpriteId } from "@/components/pixel/sprites";
import "./room-theme.css";

export interface CharacterConfig {
  baseId: SpriteId;
  skinTone: string;
  hairColor: string;
  shirtColor: string;
  pantsColor: string;
  // Extended cosmetic fields kept for back-compat — not shown in UI.
  hairStyle?: string;
  accessory?: string;
  accentColor?: string;
}

interface CharacterCreatorProps {
  value: CharacterConfig;
  onChange: (cfg: CharacterConfig) => void;
}

// ── Color palettes ────────────────────────────────────────────────────────────

const SKIN_TONES = [
  "#fddbb4", "#f4c98f", "#e8a96a", "#d4895a",
  "#b5714a", "#8b5e42", "#fbb6ce", "#ebf8ff",
];

const HAIR_COLORS = [
  "#2d2d2d", "#4a2f17", "#744210", "#c05621",
  "#e2e8f0", "#f6e05e", "#702459", "#4a9eff",
];

const SHIRT_COLORS = [
  "#2d3748", "#3182ce", "#4f8a4e", "#ed64a6",
  "#553c9a", "#ffffff", "#ed8936", "#e53e3e",
];

const PANTS_COLORS = [
  "#33271a", "#1a202c", "#718096", "#276749",
  "#44337a", "#2c5282", "#000000", "#4a5568",
];

// Quick presets — set the 4 colors + keep baseId as default "analyst"
const PRESETS: { label: string; cfg: Omit<CharacterConfig, "baseId"> & { baseId: SpriteId } }[] = [
  {
    label: "Analyst",
    cfg: {
      baseId: "analyst",
      skinTone: "#f4c98f",
      hairColor: "#744210",
      shirtColor: "#3182ce",
      pantsColor: "#2c5282",
    },
  },
  {
    label: "Engineer",
    cfg: {
      baseId: "coder",
      skinTone: "#e8a96a",
      hairColor: "#2d2d2d",
      shirtColor: "#4f8a4e",
      pantsColor: "#33271a",
    },
  },
  {
    label: "Designer",
    cfg: {
      baseId: "designer",
      skinTone: "#fbb6ce",
      hairColor: "#702459",
      shirtColor: "#ed64a6",
      pantsColor: "#1a202c",
    },
  },
  {
    label: "Manager",
    cfg: {
      baseId: "manager",
      skinTone: "#f4c98f",
      hairColor: "#2d2d2d",
      shirtColor: "#ffffff",
      pantsColor: "#2d3748",
    },
  },
];

// ── Component ─────────────────────────────────────────────────────────────────

export function CharacterCreator({ value, onChange }: CharacterCreatorProps) {
  const [walking, setWalking] = useState(false);

  const lpcLook = useMemo(
    () =>
      getLpcLook(value.baseId, 0, {
        baseId: value.baseId,
        skinTone: value.skinTone,
        hairColor: value.hairColor,
        shirtColor: value.shirtColor,
        pantsColor: value.pantsColor,
      }),
    [value],
  );

  const update = (partial: Partial<CharacterConfig>) => {
    onChange({ ...value, ...partial });
  };

  return (
    <div className="flex flex-col gap-4">
      {/* Live LPC preview */}
      <div className="flex flex-col items-center gap-2">
        <div
          className="border-2 border-border/60 rounded-lg overflow-hidden flex items-end justify-center"
          style={{ background: "#1e1e2e", width: 128, height: 180, paddingBottom: 14 }}
        >
          <div className={walking ? "pdr-bobber pdr-walking" : "pdr-bobber"}>
            <LpcSprite look={lpcLook} direction="down" walking={walking} scale={2} />
          </div>
        </div>
        <button
          type="button"
          onClick={() => setWalking((w) => !w)}
          className={`rounded px-2 py-1 text-[10px] font-mono transition-all ${
            walking
              ? "bg-blue-500/20 border border-blue-400/60 text-blue-300"
              : "bg-muted/40 border border-border/40 text-muted-foreground hover:border-border"
          }`}
        >
          {walking ? "Walking" : "Idle"}
        </button>
      </div>

      {/* Quick presets */}
      <div>
        <p className="text-xs font-mono text-muted-foreground mb-2 uppercase tracking-wider">
          Quick Presets
        </p>
        <div className="flex gap-1.5 flex-wrap">
          {PRESETS.map((p) => (
            <button
              key={p.label}
              onClick={() => onChange({ ...value, ...p.cfg })}
              className="rounded px-2 py-1 text-[10px] font-mono bg-muted/40 border border-border/40 text-muted-foreground hover:border-yellow-400/60 hover:text-yellow-300 transition-all"
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* Color pickers */}
      <ColorRow
        label="Skin Tone"
        colors={SKIN_TONES}
        selected={value.skinTone}
        onSelect={(c) => update({ skinTone: c })}
      />
      <ColorRow
        label="Hair Color"
        colors={HAIR_COLORS}
        selected={value.hairColor}
        onSelect={(c) => update({ hairColor: c })}
      />
      <ColorRow
        label="Shirt"
        colors={SHIRT_COLORS}
        selected={value.shirtColor}
        onSelect={(c) => update({ shirtColor: c })}
      />
      <ColorRow
        label="Pants"
        colors={PANTS_COLORS}
        selected={value.pantsColor}
        onSelect={(c) => update({ pantsColor: c })}
      />
    </div>
  );
}

// ── Color row ─────────────────────────────────────────────────────────────────

function ColorRow({
  label,
  colors,
  selected,
  onSelect,
}: {
  label: string;
  colors: string[];
  selected: string;
  onSelect: (c: string) => void;
}) {
  return (
    <div>
      <p className="text-xs font-mono text-muted-foreground mb-1.5 uppercase tracking-wider">
        {label}
      </p>
      <div className="flex gap-1.5 flex-wrap">
        {colors.map((color) => (
          <button
            key={color}
            onClick={() => onSelect(color)}
            title={color}
            className={`rounded-full transition-all ${
              selected === color
                ? "ring-2 ring-offset-1 ring-yellow-400 ring-offset-background"
                : "hover:ring-1 hover:ring-border"
            }`}
            style={{
              width: 20,
              height: 20,
              background: color,
              border: "1px solid rgba(255,255,255,0.15)",
              imageRendering: "pixelated",
            }}
          />
        ))}
      </div>
    </div>
  );
}
