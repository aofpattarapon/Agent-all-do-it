/**
 * Pixel art sprite definitions — 16×16 grids encoded as hex color arrays.
 * Each sprite is a flat array of 256 entries (row-major).
 * "" = transparent.
 */

export type SpriteId =
  | "coder" | "analyst" | "designer" | "manager" | "qa_bot"
  | "devops" | "wizard" | "robot" | "ninja" | "scientist"
  | "architect" | "writer" | "detective" | "captain" | "ghost";

interface Sprite {
  id: SpriteId;
  label: string;
  // 2-char hex shorthand palette — maps single char → hex color
  palette: Record<string, string>;
  // 16×16 = 256 chars, each char maps to palette or "" for transparent
  pixels: string;
}

const T = ""; // transparent

export const SPRITES: Record<SpriteId, Sprite> = {
  coder: {
    id: "coder",
    label: "Coder",
    palette: {
      "h": "#f4c98f", // skin
      "H": "#e8a96a", // skin dark
      "b": "#2d3748", // dark shirt
      "B": "#1a202c", // darker
      "g": "#68d391", // green (screen glow)
      "G": "#38a169",
      "s": "#e2e8f0", // silver
      "e": "#63b3ed", // eye blue
      "k": "#2d2d2d", // black hair
      "w": "#ffffff",
      "r": "#fc8181",
    },
    pixels:
      "....kkkkkkkk...." +
      "...kkkkkkkkkkk.." +
      "..kkhhhhhhhhhkk." +
      "..khhhhhhhhhhhk." +
      "..khhehhhhehhhk." +
      "..khhhhhhhhhhkk." +
      "..khhhrrhhhhhk.." +
      "...khhhhhhhhk..." +
      "....bbbbbbbb...." +
      "...bbbbbbbbbb..." +
      "..bbbggggggbbb.." +
      "..bbgggggggbbb.." +
      "...bbbbbbbbbb..." +
      "..bbb....bbb...." +
      "..bbb....bbb...." +
      "..ss.....ss....."
  },
  analyst: {
    id: "analyst",
    label: "Analyst",
    palette: {
      "h": "#f4c98f",
      "H": "#e8a96a",
      "b": "#3182ce",
      "B": "#2b6cb0",
      "s": "#e2e8f0",
      "e": "#2d3748",
      "k": "#744210",
      "p": "#9f7aea",
      "w": "#ffffff",
      "r": "#fc8181",
      "y": "#f6e05e",
    },
    pixels:
      "....kkkkkkkk...." +
      "...kkkkkkkkkkk.." +
      "..kkhhhhhhhhhkk." +
      "..khhhhhhhhhhhk." +
      "..khhehhhhhehhk." +
      "..khhhhhhhhhhkk." +
      "..khhhrrhhhhhk.." +
      "...khhhhhhhhk..." +
      "....bbbbbbbb...." +
      "...bbbbbbbbbbb.." +
      "..bbbbyyyyybbbb." +
      "..bbbyyyyyyybb.." +
      "...bbbbbbbbbb..." +
      "..bbb....bbb...." +
      "..bbb....bbb...." +
      "..ss.....ss....."
  },
  designer: {
    id: "designer",
    label: "Designer",
    palette: {
      "h": "#fbb6ce",
      "H": "#f687b3",
      "b": "#ed64a6",
      "B": "#d53f8c",
      "s": "#e2e8f0",
      "e": "#2d3748",
      "k": "#702459",
      "p": "#9f7aea",
      "w": "#ffffff",
      "r": "#fc8181",
      "a": "#fefcbf",
    },
    pixels:
      "....kkkkkkkk...." +
      "...kkkkkkkkkkk.." +
      "..kkhhhhhhhhhkk." +
      "..khhhhhhhhhhhk." +
      "..khhehhhhhehhk." +
      "..khhhhhhhhhhkk." +
      "..khhhrrhhhhhk.." +
      "...khhhhhhhhk..." +
      "....bbbbbbbb...." +
      "...bbbbbbbbbbb.." +
      "..bbbpaappabbb.." +
      "..bbbaaaaapbb..." +
      "...bbbbbbbbbb..." +
      "..bbb....bbb...." +
      "..bbb....bbb...." +
      "..ss.....ss....."
  },
  manager: {
    id: "manager",
    label: "Manager",
    palette: {
      "h": "#f4c98f",
      "H": "#e8a96a",
      "b": "#2d3748",
      "B": "#1a202c",
      "s": "#e2e8f0",
      "e": "#2d3748",
      "k": "#2d2d2d",
      "t": "#718096",
      "w": "#ffffff",
      "r": "#e53e3e",
      "c": "#4299e1",
    },
    pixels:
      "....kkkkkkkk...." +
      "...kkkkkkkkkkk.." +
      "..kkhhhhhhhhhkk." +
      "..khhhhhhhhhhhk." +
      "..khhehhhhhehkk." +
      "..khhhhhhhhhhkk." +
      "..khhhrrhhhhhk.." +
      "...khhhhhhhhk..." +
      "....bbbbbbbb...." +
      "..cwwbbbbbbwwc.." +
      "..cwbbbbbbbwc..." +
      "..cbbbbbbbbbbc.." +
      "..wbbbbbbbbbbw.." +
      "..bbb....bbb...." +
      "..bbb....bbb...." +
      "..ss.....ss....."
  },
  qa_bot: {
    id: "qa_bot",
    label: "QA Bot",
    palette: {
      "h": "#f4c98f",
      "s": "#e2e8f0",
      "e": "#2d3748",
      "b": "#38a169",
      "B": "#276749",
      "k": "#2d2d2d",
      "r": "#fc8181",
      "g": "#68d391",
      "w": "#ffffff",
      "x": "#e53e3e",
    },
    pixels:
      "....kkkkkkkk...." +
      "...kkkkkkkkkkk.." +
      "..kkhhhhhhhhhkk." +
      "..khhhhhhhhhhhk." +
      "..khhehhhhhehkk." +
      "..khhhhhhhhhhkk." +
      "..khhhrrhhhhhk.." +
      "...khhhhhhhhk..." +
      "....bbbbbbbb...." +
      "...bbbbbbbbbbb.." +
      "..bbbgxgxgxbbbb." +
      "..bbgxgxgxgbb..." +
      "...bbbbbbbbbb..." +
      "..bbb....bbb...." +
      "..bbb....bbb...." +
      "..ss.....ss....."
  },
  devops: {
    id: "devops",
    label: "DevOps",
    palette: {
      "h": "#f4c98f",
      "s": "#a0aec0",
      "e": "#2d3748",
      "b": "#4a5568",
      "B": "#2d3748",
      "k": "#1a202c",
      "o": "#ed8936",
      "O": "#c05621",
      "w": "#ffffff",
      "r": "#fc8181",
    },
    pixels:
      "....kkkkkkkk...." +
      "...kkkkkkkkkkk.." +
      "..kkhhhhhhhhhkk." +
      "..khhhhhhhhhhhk." +
      "..khhehhhhhehkk." +
      "..khhhhhhhhhhkk." +
      "..khhhrrhhhhhk.." +
      "...khhhhhhhhk..." +
      "....bbbbbbbb...." +
      "...bbbbbbbbbbb.." +
      "..bbbOoooObbbb.." +
      "..bbooooooobb..." +
      "...bbbbbbbbbb..." +
      "..bBB....BBb...." +
      "..bBB....BBb...." +
      "..ss.....ss....."
  },
  wizard: {
    id: "wizard",
    label: "Wizard",
    palette: {
      "h": "#f4c98f",
      "s": "#e2e8f0",
      "e": "#9f7aea",
      "b": "#553c9a",
      "B": "#44337a",
      "k": "#322659",
      "p": "#9f7aea",
      "P": "#6b46c1",
      "w": "#ffffff",
      "y": "#f6e05e",
      "r": "#fc8181",
    },
    pixels:
      "......yyyy......" +
      "....yyyyyyyy...." +
      "...yykhhhhhkyy.." +
      "..yykhhhhhhkyy.." +
      "..ykhhehhhheky.." +
      "..ykhhhhhhhhky.." +
      "..ykhhhrrhhhky.." +
      "...ykhhhhhhky..." +
      "....bbbbbbbb...." +
      "...bbbpppbbbbb.." +
      "..bbppppppppbb.." +
      "..bpppppppppbb.." +
      "...bbbbbbbbbb..." +
      "..bbb....bbb...." +
      "..bBB....BBb...." +
      "..ss.....ss....."
  },
  robot: {
    id: "robot",
    label: "Robot",
    palette: {
      "h": "#a0aec0",
      "H": "#718096",
      "s": "#e2e8f0",
      "e": "#63b3ed",
      "E": "#4299e1",
      "b": "#2d3748",
      "B": "#1a202c",
      "k": "#4a5568",
      "g": "#68d391",
      "w": "#ffffff",
      "y": "#f6e05e",
    },
    pixels:
      "....kkkkkkkk...." +
      "...khhhhhhhhk..." +
      "..khhhhhhhhhhhk." +
      "..khheEhhhEehhk." +
      "..khhEEhhhEEhhk." +
      "..khhhhhhhhhhkk." +
      "..khhgggggghhhk." +
      "...khhhhhhhhk..." +
      "....bbbbbbbb...." +
      "..kbbbbbbbbbbbk." +
      "..kbbyyyyyybbkk." +
      "..kbyyyyyyybbk.." +
      "...kbbbbbbbbbk.." +
      "..kbbb....kbbb.." +
      "..kbbb....kbbb.." +
      "..kss.....kss..."
  },
  ninja: {
    id: "ninja",
    label: "Ninja",
    palette: {
      "h": "#f4c98f",
      "s": "#e2e8f0",
      "e": "#2d3748",
      "b": "#1a202c",
      "B": "#000000",
      "k": "#2d2d2d",
      "r": "#e53e3e",
      "w": "#ffffff",
      "g": "#68d391",
    },
    pixels:
      "....kkkkkkkk...." +
      "...kkbbbbbbbbkk." +
      "..kbbbbbbbbbbbk." +
      "..kbhhbbbbbbhbk." +
      "..kbhhhbbbbhhbk." +
      "..kbbbbbbbbbbk.." +
      "..kbbbrrbbbbbk.." +
      "...kbbbbbbbbk..." +
      "....bbbbbbbb...." +
      "...bbbbbbbbbbb.." +
      "..bbbbbbbbbbbbb." +
      "..bbbbbbbbbbbb.." +
      "...bbbbbbbbbb..." +
      "..bbb....bbb...." +
      "..bBB....BBb...." +
      "..ss.....ss....."
  },
  scientist: {
    id: "scientist",
    label: "Scientist",
    palette: {
      "h": "#f4c98f",
      "s": "#e2e8f0",
      "e": "#2d3748",
      "b": "#ffffff",
      "B": "#e2e8f0",
      "k": "#2d2d2d",
      "r": "#fc8181",
      "g": "#68d391",
      "G": "#38a169",
      "p": "#9f7aea",
      "y": "#f6e05e",
    },
    pixels:
      "....kkkkkkkk...." +
      "...kkkkkkkkkkk.." +
      "..kkhhhhhhhhhkk." +
      "..khhhhhhhhhhhk." +
      "..khhehhhhhehkk." +
      "..khhhhhhhhhhkk." +
      "..khhhrrhhhhhk.." +
      "...khhhhhhhhk..." +
      "....bbbbbbbb...." +
      "...bbbbbbbbbbb.." +
      "..bbbpGpGpbbbb.." +
      "..bbGpGpGpbb...." +
      "...bbbbbbbbbb..." +
      "..bBB....BBb...." +
      "..bBB....BBb...." +
      "..ss.....ss....."
  },
  architect: {
    id: "architect",
    label: "Architect",
    palette: {
      "h": "#f4c98f",
      "s": "#e2e8f0",
      "e": "#2d3748",
      "b": "#744210",
      "B": "#5a3009",
      "k": "#2d2d2d",
      "r": "#fc8181",
      "y": "#f6e05e",
      "w": "#ffffff",
      "c": "#4299e1",
    },
    pixels:
      "....kkkkkkkk...." +
      "...kkkkkkkkkkk.." +
      "..kkhhhhhhhhhkk." +
      "..khhhhhhhhhhhk." +
      "..khhehhhhhehkk." +
      "..khhhhhhhhhhkk." +
      "..khhhrrhhhhhk.." +
      "...khhhhhhhhk..." +
      "....bbbbbbbb...." +
      "...bbbbbbbbbbb.." +
      "..bbbycycybbbb.." +
      "..bbycycycybbb.." +
      "...bbbbbbbbbb..." +
      "..bBB....BBb...." +
      "..bBB....BBb...." +
      "..ss.....ss....."
  },
  writer: {
    id: "writer",
    label: "Writer",
    palette: {
      "h": "#f4c98f",
      "s": "#e2e8f0",
      "e": "#2d3748",
      "b": "#2b6cb0",
      "B": "#2c5282",
      "k": "#744210",
      "r": "#fc8181",
      "w": "#ffffff",
      "p": "#9f7aea",
    },
    pixels:
      "....kkkkkkkk...." +
      "...kkkkkkkkkkk.." +
      "..kkhhhhhhhhhkk." +
      "..khhhhhhhhhhhk." +
      "..khhehhhhhehkk." +
      "..khhhhhhhhhhkk." +
      "..khhhrrhhhhhk.." +
      "...khhhhhhhhk..." +
      "....bbbbbbbb...." +
      "...bbbbbbbbbbb.." +
      "..bbbwwwwwwbbbb." +
      "..bbwwwwwwwbb..." +
      "...bbbbbbbbbb..." +
      "..bBB....BBb...." +
      "..bBB....BBb...." +
      "..ss.....ss....."
  },
  detective: {
    id: "detective",
    label: "Detective",
    palette: {
      "h": "#f4c98f",
      "s": "#e2e8f0",
      "e": "#2d3748",
      "b": "#4a5568",
      "B": "#2d3748",
      "k": "#1a202c",
      "r": "#e53e3e",
      "w": "#ffffff",
      "y": "#f6e05e",
    },
    pixels:
      "....kkkkkkkk...." +
      "..kkkkkkkkkkkkk." +
      ".kkkkkhhhhhhkkkk" +
      "..kkhhhhhhhhhkk." +
      "..khhhehhhehhhk." +
      "..khhhhhhhhhhkk." +
      "..khhhrrhhhhhk.." +
      "...khhhhhhhhk..." +
      "....bbbbbbbb...." +
      "...bbbbbbbbbbb.." +
      "..bbbyyyyyybbbbb" +
      "..bbyyyyyyyybb.." +
      "...bbbbbbbbbb..." +
      "..bBB....BBb...." +
      "..bBB....BBb...." +
      "..ss.....ss....."
  },
  captain: {
    id: "captain",
    label: "Captain",
    palette: {
      "h": "#f4c98f",
      "s": "#e2e8f0",
      "e": "#2d3748",
      "b": "#2c5282",
      "B": "#2a4365",
      "k": "#1a202c",
      "r": "#e53e3e",
      "w": "#ffffff",
      "y": "#f6e05e",
      "g": "#68d391",
    },
    pixels:
      "...bbbbbbbbbbb.." +
      "..bbbbbbbbbbbbb." +
      "..kkhhhhhhhhhkk." +
      "..khhhhhhhhhhhk." +
      "..khhhehhhehhhk." +
      "..khhhhhhhhhhkk." +
      "..khhhrrhhhhhk.." +
      "...khhhhhhhhk..." +
      "....bbbbbbbb...." +
      "..bwbbbbbbbbwb.." +
      "..bwwbbbbbbbwb.." +
      "..bbbbbbbbbbbb.." +
      "...bbbbbbbbbb..." +
      "..bBB....BBb...." +
      "..bBB....BBb...." +
      "..ss.....ss....."
  },
  ghost: {
    id: "ghost",
    label: "Ghost",
    palette: {
      "h": "#ebf8ff",
      "H": "#bee3f8",
      "s": "#e2e8f0",
      "e": "#2d3748",
      "b": "#63b3ed",
      "B": "#4299e1",
      "k": "#2b6cb0",
      "r": "#fc8181",
      "w": "#ffffff",
      "p": "#9f7aea",
    },
    pixels:
      "....hhhhhhhh...." +
      "...hhhhhhhhhhhh." +
      "..hhhhhhhhhhhhhh" +
      "..hhhhhhhhhhhhh." +
      "..hhhehhhhhehhhh" +
      "..hhhhhhhhhhhhh." +
      "..hhhhrrhhhhhhhh" +
      "...hhhhhhhhhh..." +
      "....bbbbbbbb...." +
      "...bbbbbbbbbbb.." +
      "..bbbpppppbbbbb." +
      "..bbbpppppbbbbb." +
      "..bbbbbbbbbbbbb." +
      "....bb..bb..bb.." +
      "...bbb..bbb....." +
      "................"
  },
};

export const SPRITE_IDS = Object.keys(SPRITES) as SpriteId[];

/** Render sprite pixels as a flat array of {x, y, color} for SVG rendering. */
export function getSpritePixels(id: SpriteId): Array<{ x: number; y: number; color: string }> {
  const sprite = SPRITES[id];
  if (!sprite) return [];
  const pixels: Array<{ x: number; y: number; color: string }> = [];
  const { palette, pixels: raw } = sprite;
  // Pad or trim to exactly 256 chars
  const padded = raw.replace(/\s/g, "").padEnd(256, ".").slice(0, 256);
  for (let i = 0; i < 256; i++) {
    const ch = padded[i] ?? ".";
    if (ch === "." || ch === " ") continue;
    const color = palette[ch];
    if (!color) continue;
    pixels.push({ x: i % 16, y: Math.floor(i / 16), color });
  }
  return pixels;
}
