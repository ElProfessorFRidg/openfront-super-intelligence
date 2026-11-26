// Environnement headless OpenFront : reset / step / snapshot / restore / result.
// Construit sur le moteur officiel épinglé (GameRunner). Aucune réécriture du moteur.
import { Difficulty, GameMapSize, GameMapType, GameMode, GameType } from "@openfront/engine-api/game/GameTypes";
import { GameUpdateType, HashUpdate } from "@openfront/engine-api/game/GameUpdates";
import type { GameConfig, GameStartInfo, StampedIntent } from "@openfront/engine-api/Schemas";
import { loadMapFiles } from "@openfront/shared/GameMapLoader";
import { createGameRunner, createGameRunnerFromSnapshot, GameRunner } from "@openfront/engine/GameRunner";
import path from "path";
import { NodeGameMapLoader } from "../tests/perf/fullgame/NodeGameMapLoader";

const MAPS_DIR = path.resolve(process.cwd(), "resources/maps");

const MAP_CACHE = new Map<string, any>(); // cartes statiques immuables partagées entre parties du même processus

export interface ResetOptions {
  map: string;            // clé GameMapType, ex. "World"
  seed: string;           // 8-10 alphanum (GAME_ID_REGEX)
  agents: number;         // joueurs pilotés de l'extérieur
  bots: number;
  nations?: "default" | "disabled" | number;
  difficulty?: keyof typeof Difficulty;
  /** SCENARIOS DE TEST UNIQUEMENT (ex. infiniteGold, instantBuild). Interdit pour l'entrainement et l'evaluation. */
  overrides?: Record<string, unknown>;
}

export const agentId = (i: number) => `agentAA${String(i).padStart(2, "0")}`; // 8 car.

export class OFEnv {
  runner!: GameRunner;
  gameStart!: GameStartInfo;
  turn = 0;
  lastHash: HashUpdate | undefined;
  error: string | undefined;
  private mapFiles!: Awaited<ReturnType<typeof loadMapFiles>>;

  private cb = (gu: any) => {
    if ("errMsg" in gu) { this.error = `${gu.errMsg}\n${gu.stack ?? ""}`; return; }
    const hs = gu.updates[GameUpdateType.Hash] as HashUpdate[];
    if (hs.length) this.lastHash = hs[hs.length - 1];
  };

  async reset(o: ResetOptions) {
    console.debug = () => {};
    const mapType = GameMapType[o.map as keyof typeof GameMapType];
    if (!mapType) throw new Error(`carte inconnue: ${o.map}`);
    const config: GameConfig = {
      gameMap: mapType, gameMapSize: GameMapSize.Normal, gameMode: GameMode.FFA,
      gameType: GameType.Public, difficulty: Difficulty[o.difficulty ?? "Medium"],
      nations: o.nations ?? "default", donateGold: true, donateTroops: true,
      bots: o.bots, infiniteGold: false, infiniteTroops: false, instantBuild: false, randomSpawn: false,
    } as GameConfig;
    if (o.overrides) Object.assign(config, o.overrides);
    this.gameStart = {
      gameID: o.seed, lobbyCreatedAt: 0, config,
      players: Array.from({ length: o.agents }, (_, i) => ({ clientID: agentId(i), username: `Agent${i}` })),
    } as GameStartInfo;
    const key = `${config.gameMap}|${config.gameMapSize}`;
    let mf = MAP_CACHE.get(key);
    if (!mf) { mf = await loadMapFiles(new NodeGameMapLoader(MAPS_DIR), config.gameMap, config.gameMapSize); MAP_CACHE.set(key, mf); }
    this.mapFiles = mf;
    this.runner = await createGameRunner(this.gameStart, undefined, this.mapFiles, this.cb);
    this.turn = 0; this.error = undefined; this.lastHash = undefined;
  }

  get game() { return this.runner.game; }
  get tick() { return this.game.ticks(); }

  /** Avance d'un tick avec les intents donnés (stampés par clientID). */
  stepTick(intents: Omit<StampedIntent, never>[] = []): boolean {
    this.runner.addTurn({ turnNumber: this.turn++, intents: intents as StampedIntent[] });
    return this.runner.executeNextTick() && this.error === undefined;
  }

  snapshot(): Uint8Array { return this.runner.snapshot("osi"); }

  async restore(snap: Uint8Array) {
    this.error = undefined; this.lastHash = undefined;
    this.runner = await createGameRunnerFromSnapshot(this.gameStart, snap, undefined, this.mapFiles, this.cb);
    this.turn = this.game.ticks(); // « le premier tour ajouté est le tour du tick du snapshot »
  }
}
