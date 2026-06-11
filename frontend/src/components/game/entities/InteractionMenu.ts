// @ts-nocheck
import * as Phaser from "phaser";

export interface MenuOption {
  label: string;
  action: () => void;
}

const MENU_WIDTH = 180;
const ITEM_HEIGHT = 34;
const FONT_SIZE = "15px";
const PAD_X = 14;
const PAD_Y = 8;
const BG_COLOR = 0x120e04;
const BORDER_COLOR = 0xc9a227;
const HIGHLIGHT_FILL = 0x2e2408;
const HIGHLIGHT_BORDER = 0xf5e6b3;
const TEXT_COLOR = "#d4c9a8";
const TEXT_HIGHLIGHT = "#ffffff";
const DEPTH = 30;
const ABOVE_WORKER_PX = 50;

export class InteractionMenu {
  private container: Phaser.GameObjects.Container;
  private bg: Phaser.GameObjects.Graphics;
  private items: Phaser.GameObjects.Text[] = [];
  private highlights: Phaser.GameObjects.Graphics[] = [];
  private scene: Phaser.Scene;
  private options: MenuOption[] = [];
  private selectedIndex = 0;
  private _visible = false;
  private openFrame = 0;
  private totalH = 0;
  private trackedSprite: { x: number; y: number } | null = null;

  private upKey: Phaser.Input.Keyboard.Key;
  private downKey: Phaser.Input.Keyboard.Key;
  private upArrow: Phaser.Input.Keyboard.Key;
  private downArrow: Phaser.Input.Keyboard.Key;
  private enterKey: Phaser.Input.Keyboard.Key;
  private escKey: Phaser.Input.Keyboard.Key;

  onClose: (() => void) | null = null;

  // Arrow function so `this` is always the instance — needed for reliable add/remove
  private readonly _handlePointerDown = (pointer) => {
    if (!this._visible) return;
    // Ignore clicks fired on the same frame we opened (prevents immediate close)
    if (this.scene.game.getFrame() - this.openFrame < 3) return;

    const mx = this.container.x;
    const my = this.container.y;
    const px = pointer.x;
    const py = pointer.y;

    // Click outside the menu → close
    if (px < mx - 4 || px > mx + MENU_WIDTH + 4 || py < my - 4 || py > my + this.totalH + 4) {
      this.hide();
      this.onClose?.();
      return;
    }

    // Click inside → find which row was hit
    const localY = py - my - PAD_Y;
    const idx = Math.floor(localY / ITEM_HEIGHT);
    if (idx >= 0 && idx < this.options.length) {
      this.selectedIndex = idx;
      this.updateHighlight();
      // Brief visual highlight before firing action
      this.scene.time.delayedCall(60, () => {
        const opt = this.options[idx];
        if (opt) { this.hide(); opt.action(); }
      });
    }
  };

  constructor(scene: Phaser.Scene) {
    this.scene = scene;
    this.bg = scene.add.graphics();
    this.container = scene.add.container(0, 0, [this.bg]);
    this.container.setDepth(DEPTH);
    this.container.setVisible(false);
    this.container.setScrollFactor(0);

    const kb = scene.input.keyboard;
    if (!kb) throw new Error("Keyboard plugin not available");
    this.upKey = kb.addKey(Phaser.Input.Keyboard.KeyCodes.W, false);
    this.downKey = kb.addKey(Phaser.Input.Keyboard.KeyCodes.S, false);
    this.upArrow = kb.addKey(Phaser.Input.Keyboard.KeyCodes.UP, false);
    this.downArrow = kb.addKey(Phaser.Input.Keyboard.KeyCodes.DOWN, false);
    this.enterKey = kb.addKey(Phaser.Input.Keyboard.KeyCodes.ENTER, false);
    this.escKey = kb.addKey(Phaser.Input.Keyboard.KeyCodes.ESC, false);

    scene.input.on("pointerdown", this._handlePointerDown);
  }

  get visible(): boolean {
    return this._visible;
  }

  /** Only pass enabled options — disabled items are filtered out by the caller. */
  show(sprite: { x: number; y: number }, options: MenuOption[]) {
    this.options = options;
    this.trackedSprite = sprite;
    this.selectedIndex = 0;
    this.openFrame = this.scene.game.getFrame();

    this.clearItems();

    this.totalH = options.length * ITEM_HEIGHT + PAD_Y * 2;

    // Gold pixel-art frame: solid gold outer → dark bg → faint inner line
    this.bg.clear();
    this.bg.fillStyle(BORDER_COLOR, 1);
    this.bg.fillRoundedRect(-3, -3, MENU_WIDTH + 6, this.totalH + 6, 7);
    this.bg.fillStyle(BG_COLOR, 0.97);
    this.bg.fillRoundedRect(0, 0, MENU_WIDTH, this.totalH, 4);
    this.bg.lineStyle(1, 0x4a3c10, 1);
    this.bg.strokeRoundedRect(3, 3, MENU_WIDTH - 6, this.totalH - 6, 2);

    for (let i = 0; i < options.length; i++) {
      const y = PAD_Y + i * ITEM_HEIGHT;

      const highlight = this.scene.add.graphics();
      highlight.fillStyle(HIGHLIGHT_FILL, 1);
      highlight.fillRoundedRect(3, y + 3, MENU_WIDTH - 6, ITEM_HEIGHT - 6, 3);
      highlight.lineStyle(1, HIGHLIGHT_BORDER, 0.9);
      highlight.strokeRoundedRect(3, y + 3, MENU_WIDTH - 6, ITEM_HEIGHT - 6, 3);
      highlight.setVisible(false);
      this.highlights.push(highlight);
      this.container.add(highlight);

      const txt = this.scene.add.text(PAD_X, y + ITEM_HEIGHT / 2, options[i].label, {
        fontFamily: '"Pixelify Sans", "VT323", monospace',
        fontSize: FONT_SIZE,
        color: TEXT_COLOR,
      });
      txt.setResolution(window.devicePixelRatio * 2);
      txt.setOrigin(0, 0.5);
      this.items.push(txt);
      this.container.add(txt);
    }

    this.updateHighlight();
    this._syncPosition();

    this.container.setVisible(true);
    this._visible = true;
  }

  hide() {
    this.container.setVisible(false);
    this._visible = false;
    this.trackedSprite = null;
    this.clearItems();
  }

  /** Recalculate screen position so the menu floats above the agent as it moves. */
  private _syncPosition() {
    if (!this.trackedSprite) return;
    const cam = this.scene.cameras.main;
    const screenX = (this.trackedSprite.x - cam.scrollX) * cam.zoom;
    const screenY = (this.trackedSprite.y - cam.scrollY) * cam.zoom;

    const menuX = Math.max(Math.min(screenX - MENU_WIDTH / 2, cam.width - MENU_WIDTH - 8), 8);
    const menuY = Math.max(screenY - this.totalH - ABOVE_WORKER_PX, 8);

    this.container.setPosition(menuX, menuY);
  }

  update() {
    if (!this._visible) return;

    // Follow the agent every frame
    this._syncPosition();

    const elapsed = this.scene.game.getFrame() - this.openFrame;
    if (elapsed < 2) return;

    if (Phaser.Input.Keyboard.JustDown(this.upKey) || Phaser.Input.Keyboard.JustDown(this.upArrow)) {
      this.moveSelection(-1);
    } else if (Phaser.Input.Keyboard.JustDown(this.downKey) || Phaser.Input.Keyboard.JustDown(this.downArrow)) {
      this.moveSelection(1);
    }

    if (Phaser.Input.Keyboard.JustDown(this.enterKey)) {
      const opt = this.options[this.selectedIndex];
      if (opt) { this.hide(); opt.action(); }
    }

    if (Phaser.Input.Keyboard.JustDown(this.escKey)) {
      this.hide();
      this.onClose?.();
    }
  }

  private moveSelection(dir: number) {
    const len = this.options.length;
    if (len === 0) return;
    this.selectedIndex = (this.selectedIndex + dir + len) % len;
    this.updateHighlight();
  }

  private updateHighlight() {
    for (let i = 0; i < this.highlights.length; i++) {
      const selected = i === this.selectedIndex;
      this.highlights[i].setVisible(selected);
      this.items[i]?.setColor(selected ? TEXT_HIGHLIGHT : TEXT_COLOR);
    }
  }

  private clearItems() {
    for (const t of this.items) t.destroy();
    for (const h of this.highlights) h.destroy();
    this.items = [];
    this.highlights = [];
  }

  destroy() {
    this.clearItems();
    this.container.destroy();
    this.scene.input.off("pointerdown", this._handlePointerDown);

    const kb = this.scene.input.keyboard;
    if (kb) {
      kb.removeKey(this.upKey, true);
      kb.removeKey(this.downKey, true);
      kb.removeKey(this.upArrow, true);
      kb.removeKey(this.downArrow, true);
      kb.removeKey(this.enterKey, true);
      kb.removeKey(this.escKey, true);
    }
    this.onClose = null;
  }
}
