import * as Phaser from "phaser";
import { Worker } from "../entities/Worker";
import { Player } from "../entities/Player";
import { gameEvents } from "@/lib/game/events";
import type { WorkerManager } from "./WorkerManager";
import type { CameraController } from "./CameraController";

export class InteractionManager {
  private scene: Phaser.Scene;
  private player: Player;
  private workerManager: WorkerManager;
  private cameraController: CameraController;

  nearestWorker: Worker | null = null;

  constructor(
    scene: Phaser.Scene,
    player: Player,
    workerManager: WorkerManager,
    cameraController: CameraController,
  ) {
    this.scene = scene;
    this.player = player;
    this.workerManager = workerManager;
    this.cameraController = cameraController;
  }

  /** No Phaser menu to init — menu is a React DOM overlay. */
  initInteractionUI() {
    // no-op
  }

  openWorkerMenu(worker: Worker, clientX: number, clientY: number) {
    gameEvents.emit("agent-menu-open", {
      seatId: worker.seatId,
      status: worker.status,
      assignedRunId: worker.assignedRunId,
      clientX,
      clientY,
    });
  }

  openWorkerMenuAtSprite(worker: Worker, clientX = 0, clientY = 0) {
    this.openWorkerMenu(worker, clientX, clientY);
  }

  findNearestWorker(): Worker | null {
    return null;
  }

  /** No-op — proximity-based interaction removed; click-only. */
  updateProximity(_eKey: Phaser.Input.Keyboard.Key): boolean {
    return false;
  }

  clearIfNearest(worker: Worker) {
    if (this.nearestWorker === worker) this.nearestWorker = null;
  }

  destroy() {
    this.nearestWorker = null;
  }
}
