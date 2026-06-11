/**
 * Character type definitions for the pixel art virtual office.
 * Each character has a base style and color palette for canvas drawing.
 */

import type { SpriteId } from "@/components/pixel/sprites";

export interface CharacterDef {
  id: SpriteId;
  label: string;
  skinTone: string;
  hairColor: string;
  shirtColor: string;
  shirtAccent: string;
  pantsColor: string;
  shoeColor: string;
  accentColor: string;
  style: "human" | "robot" | "ghost";
}

export const CHARACTERS: Record<SpriteId, CharacterDef> = {
  coder: {
    id: "coder",
    label: "Coder",
    skinTone: "#f4c98f",
    hairColor: "#2d2d2d",
    shirtColor: "#2d3748",
    shirtAccent: "#68d391",
    pantsColor: "#1a202c",
    shoeColor: "#4a5568",
    accentColor: "#63b3ed",
    style: "human",
  },
  analyst: {
    id: "analyst",
    label: "Analyst",
    skinTone: "#f4c98f",
    hairColor: "#744210",
    shirtColor: "#3182ce",
    shirtAccent: "#f6e05e",
    pantsColor: "#718096",
    shoeColor: "#2d3748",
    accentColor: "#9f7aea",
    style: "human",
  },
  designer: {
    id: "designer",
    label: "Designer",
    skinTone: "#fbb6ce",
    hairColor: "#702459",
    shirtColor: "#ed64a6",
    shirtAccent: "#fefcbf",
    pantsColor: "#1a202c",
    shoeColor: "#553c9a",
    accentColor: "#f687b3",
    style: "human",
  },
  manager: {
    id: "manager",
    label: "Manager",
    skinTone: "#f4c98f",
    hairColor: "#2d2d2d",
    shirtColor: "#ffffff",
    shirtAccent: "#4299e1",
    pantsColor: "#2d3748",
    shoeColor: "#1a202c",
    accentColor: "#e53e3e",
    style: "human",
  },
  qa_bot: {
    id: "qa_bot",
    label: "QA Bot",
    skinTone: "#f4c98f",
    hairColor: "#2d2d2d",
    shirtColor: "#38a169",
    shirtAccent: "#68d391",
    pantsColor: "#276749",
    shoeColor: "#1a202c",
    accentColor: "#fc8181",
    style: "human",
  },
  devops: {
    id: "devops",
    label: "DevOps",
    skinTone: "#f4c98f",
    hairColor: "#1a202c",
    shirtColor: "#4a5568",
    shirtAccent: "#ed8936",
    pantsColor: "#2d3748",
    shoeColor: "#1a202c",
    accentColor: "#ed8936",
    style: "human",
  },
  wizard: {
    id: "wizard",
    label: "Wizard",
    skinTone: "#f4c98f",
    hairColor: "#e2e8f0",
    shirtColor: "#553c9a",
    shirtAccent: "#9f7aea",
    pantsColor: "#44337a",
    shoeColor: "#322659",
    accentColor: "#f6e05e",
    style: "human",
  },
  robot: {
    id: "robot",
    label: "Robot",
    skinTone: "#a0aec0",
    hairColor: "#4a5568",
    shirtColor: "#2d3748",
    shirtAccent: "#f6e05e",
    pantsColor: "#1a202c",
    shoeColor: "#4a5568",
    accentColor: "#63b3ed",
    style: "robot",
  },
  ninja: {
    id: "ninja",
    label: "Ninja",
    skinTone: "#f4c98f",
    hairColor: "#000000",
    shirtColor: "#1a202c",
    shirtAccent: "#e53e3e",
    pantsColor: "#000000",
    shoeColor: "#2d2d2d",
    accentColor: "#e53e3e",
    style: "human",
  },
  scientist: {
    id: "scientist",
    label: "Scientist",
    skinTone: "#f4c98f",
    hairColor: "#2d2d2d",
    shirtColor: "#ffffff",
    shirtAccent: "#9f7aea",
    pantsColor: "#e2e8f0",
    shoeColor: "#2d3748",
    accentColor: "#68d391",
    style: "human",
  },
  architect: {
    id: "architect",
    label: "Architect",
    skinTone: "#f4c98f",
    hairColor: "#2d2d2d",
    shirtColor: "#744210",
    shirtAccent: "#f6e05e",
    pantsColor: "#5a3009",
    shoeColor: "#2d2d2d",
    accentColor: "#4299e1",
    style: "human",
  },
  writer: {
    id: "writer",
    label: "Writer",
    skinTone: "#f4c98f",
    hairColor: "#744210",
    shirtColor: "#2b6cb0",
    shirtAccent: "#ffffff",
    pantsColor: "#2c5282",
    shoeColor: "#1a202c",
    accentColor: "#9f7aea",
    style: "human",
  },
  detective: {
    id: "detective",
    label: "Detective",
    skinTone: "#f4c98f",
    hairColor: "#1a202c",
    shirtColor: "#4a5568",
    shirtAccent: "#f6e05e",
    pantsColor: "#2d3748",
    shoeColor: "#1a202c",
    accentColor: "#f6e05e",
    style: "human",
  },
  captain: {
    id: "captain",
    label: "Captain",
    skinTone: "#f4c98f",
    hairColor: "#1a202c",
    shirtColor: "#2c5282",
    shirtAccent: "#ffffff",
    pantsColor: "#2a4365",
    shoeColor: "#1a202c",
    accentColor: "#e53e3e",
    style: "human",
  },
  ghost: {
    id: "ghost",
    label: "Ghost",
    skinTone: "#ebf8ff",
    hairColor: "#bee3f8",
    shirtColor: "#63b3ed",
    shirtAccent: "#9f7aea",
    pantsColor: "#4299e1",
    shoeColor: "#2b6cb0",
    accentColor: "#9f7aea",
    style: "ghost",
  },
};

export const CHARACTER_IDS = Object.keys(CHARACTERS) as SpriteId[];

/** Get character definition by SpriteId, falling back to robot */
export function getCharacter(id: string): CharacterDef {
  return CHARACTERS[id as SpriteId] ?? CHARACTERS.robot!;
}
