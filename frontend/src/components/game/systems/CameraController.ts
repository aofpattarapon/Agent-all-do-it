import * as Phaser from "phaser";
import { gameEvents } from "@/lib/game/events";
import {
  CAMERA_LERP,
  ZOOM_SENSITIVITY,
  ZOOM_DEFAULT,
  ZOOM_MIN,
  ZOOM_MAX,
  CAMERA_DRAG_THRESHOLD,
} from "@/lib/game/constants";

export class CameraController {
  private scene: Phaser.Scene;
  private playerSprite: Phaser.Physics.Arcade.Sprite;

  cameraDragging = false;
  cameraFollowing = true;
  mapWidth = 0;
  mapHeight = 0;

  constructor(
    scene: Phaser.Scene,
    playerSprite: Phaser.Physics.Arcade.Sprite,
    mapWidth: number,
    mapHeight: number,
  ) {
    this.scene = scene;
    this.playerSprite = playerSprite;
    this.mapWidth = mapWidth;
    this.mapHeight = mapHeight;
  }

  init() {
    const cam = this.scene.cameras.main;
    cam.setBackgroundColor("#1a1814");
    cam.setRoundPixels(true);
    cam.setZoom(ZOOM_DEFAULT);
    this.updateCameraBounds();
    // Center on map — no player to follow (player sprite is hidden)
    cam.centerOn(this.mapWidth / 2, this.mapHeight / 2);
    this.cameraFollowing = false;

    this.scene.scale.on("resize", () => this.updateCameraBounds());
    this.initWheel(cam);
    this.initCameraDrag(cam);
  }

  private initWheel(cam: Phaser.Cameras.Scene2D.Camera) {
    const canvas = this.scene.game.canvas;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const delta = e.ctrlKey ? e.deltaY * 3 : e.deltaY;
      const oldZoom = cam.zoom;
      const newZoom = Phaser.Math.Clamp(oldZoom - delta * ZOOM_SENSITIVITY, ZOOM_MIN, ZOOM_MAX);
      if (newZoom === oldZoom) return;

      if (!this.cameraFollowing) {
        const sx = e.offsetX / cam.scaleManager.displayScale.x;
        const sy = e.offsetY / cam.scaleManager.displayScale.y;
        const worldBefore = cam.getWorldPoint(sx, sy);
        cam.setZoom(newZoom);
        this.updateCameraBounds();
        const worldAfter = cam.getWorldPoint(sx, sy);
        cam.scrollX += worldBefore.x - worldAfter.x;
        cam.scrollY += worldBefore.y - worldAfter.y;
      } else {
        cam.setZoom(newZoom);
        this.updateCameraBounds();
      }
    };
    canvas.addEventListener("wheel", onWheel, { passive: false });
    this.scene.events.once("shutdown", () => canvas.removeEventListener("wheel", onWheel));

    // Zoom buttons via gameEvents
    const unsubZoomIn = gameEvents.on("camera-zoom-in", () => {
      const newZoom = Phaser.Math.Clamp(cam.zoom + 0.15, ZOOM_MIN, ZOOM_MAX);
      cam.setZoom(newZoom);
      this.updateCameraBounds();
    });
    const unsubZoomOut = gameEvents.on("camera-zoom-out", () => {
      const newZoom = Phaser.Math.Clamp(cam.zoom - 0.15, ZOOM_MIN, ZOOM_MAX);
      cam.setZoom(newZoom);
      this.updateCameraBounds();
    });
    const unsubZoomReset = gameEvents.on("camera-zoom-reset", () => {
      cam.setZoom(ZOOM_DEFAULT);
      this.updateCameraBounds();
      cam.centerOn(this.mapWidth / 2, this.mapHeight / 2);
    });
    this.scene.events.once("shutdown", () => {
      unsubZoomIn();
      unsubZoomOut();
      unsubZoomReset();
    });
  }

  initCameraDrag(cam: Phaser.Cameras.Scene2D.Camera) {
    let lastX = 0;
    let lastY = 0;

    this.scene.input.on("pointerdown", (pointer: Phaser.Input.Pointer) => {
      if (pointer.leftButtonDown()) {
        this.cameraDragging = true;
        lastX = pointer.x;
        lastY = pointer.y;
      }
    });

    this.scene.input.on("pointermove", (pointer: Phaser.Input.Pointer) => {
      if (!this.cameraDragging || !pointer.leftButtonDown()) return;

      const dx = lastX - pointer.x;
      const dy = lastY - pointer.y;
      lastX = pointer.x;
      lastY = pointer.y;

      if (Math.abs(dx) > CAMERA_DRAG_THRESHOLD || Math.abs(dy) > CAMERA_DRAG_THRESHOLD) {
        if (this.cameraFollowing) {
          cam.stopFollow();
          this.cameraFollowing = false;
        }
        cam.scrollX += dx / cam.zoom;
        cam.scrollY += dy / cam.zoom;
      }
    });

    this.scene.input.on("pointerup", () => {
      this.cameraDragging = false;
    });
  }

  resumeCameraFollow() {
    if (!this.cameraFollowing) {
      this.scene.cameras.main.startFollow(this.playerSprite, true, CAMERA_LERP, CAMERA_LERP);
      this.cameraFollowing = true;
    }
  }

  /** Recalculate camera bounds so the map is centered when viewport > map at current zoom. */
  updateCameraBounds() {
    const cam = this.scene.cameras.main;
    const viewW = cam.width / cam.zoom;
    const viewH = cam.height / cam.zoom;
    const mw = this.mapWidth;
    const mh = this.mapHeight;

    const bx = viewW > mw ? -(viewW - mw) / 2 : 0;
    const by = viewH > mh ? -(viewH - mh) / 2 : 0;
    const bw = viewW > mw ? viewW : mw;
    const bh = viewH > mh ? viewH : mh;

    cam.setBounds(bx, by, bw, bh);
  }
}
