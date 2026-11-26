// Observations légitimes + légalité des actions pour un agent. Tout vient du moteur officiel.
// Règle : uniquement ce qu'un joueur humain voit dans l'interface (pas d'état interne caché).
import { UnitType } from "@openfront/engine-api/game/GameTypes";
import type { OFEnv } from "./env.mts";
import { agentId } from "./env.mts";

const num = (b: bigint | number) => Number(b);
export const UNIT_TYPES = Object.values(UnitType) as string[];

export function playerOf(env: OFEnv, agentIdx: number) {
  return env.game.players().find((p) => p.clientID() === agentId(agentIdx));
}

/** Grille de propriété sous-échantillonnée (bloc x bloc) : smallID du propriétaire majoritaire, 0 = personne/eau. */
export function ownerGrid(env: OFEnv, block = 16): { w: number; h: number; data: number[] } {
  const m = env.game.map(), W = m.width(), H = m.height();
  const w = Math.ceil(W / block), h = Math.ceil(H / block), data = new Array<number>(w * h).fill(0);
  for (let by = 0; by < h; by++) for (let bx = 0; bx < w; bx++) {
    const votes = new Map<number, number>();
    for (let y = by * block; y < Math.min(H, (by + 1) * block); y += 2)
      for (let x = bx * block; x < Math.min(W, (bx + 1) * block); x += 2) {
        const r = m.ref(x, y);
        if (m.hasOwner(r)) { const o = m.ownerID(r); votes.set(o, (votes.get(o) ?? 0) + 1); }
      }
    let best = 0, bn = 0; for (const [o, n] of votes) if (n > bn) { best = o; bn = n; }
    data[by * w + bx] = best;
  }
  return { w, h, data };
}

export function observe(env: OFEnv, agentIdx: number, opts: { grid?: boolean; costs?: boolean } = {}) {
  const g = env.game, me = playerOf(env, agentIdx);
  if (!me) return { tick: env.tick, error: "agent introuvable" };
  const unitsByType: Record<string, number> = {};
  for (const t of UNIT_TYPES) { const c = me.unitCount(t as UnitType); if (c) unitsByType[t] = c; }
  const others = g.players().filter((p) => p !== me && p.isAlive()).map((p) => ({
    id: p.id(), smallID: p.smallID(), type: p.type(), tiles: p.numTilesOwned(), troops: Math.round(p.troops()),
    relation: me.relation(p), allied: me.isAlliedWith(p), border: me.sharesBorderWith(p), traitor: p.isTraitor(),
    canAlly: me.canSendAllianceRequest(p), incoming: me.incomingAllianceRequests().some((r: any) => r.requestor() === p),
  }));
  return {
    tick: env.tick, spawnPhase: g.inSpawnPhase(),
    self: {
      id: me.id(), smallID: me.smallID(), alive: me.isAlive(), spawned: me.hasSpawned(),
      gold: num(me.gold()), troops: Math.round(me.troops()), tiles: me.numTilesOwned(), borderTiles: me.borderTiles().size,
      tradeGold: num(me.tradeGold()), trainGold: num(me.trainGold()), goldEarned: num(me.goldEarned()),
      units: unitsByType, allies: me.allies().map((a) => a.id()),
      incomingAllianceRequests: me.incomingAllianceRequests().map((r: any) => r.requestor().id()),
    },
    others,
    costs: opts.costs ? Object.fromEntries(env.runner.playerBuildables(me.id()).map((b) => [b.type, num(b.cost)])) : undefined,
    landTotal: opts.costs ? (env as any).landTotal ??= (() => { const m = g.map(); let n = 0; for (let y = 0; y < m.height(); y += 4) for (let x = 0; x < m.width(); x += 4) if (m.isLand(m.ref(x, y))) n++; return n * 16; })() : undefined,
    ...(opts.grid ? { grid: ownerGrid(env) } : {}),
  };
}

/** Actions légales « globales » (sans tuile) : ce qui est constructible, coûts, améliorations. */
export function legalSummary(env: OFEnv, agentIdx: number) {
  const me = playerOf(env, agentIdx);
  if (!me || !me.isAlive()) return { alive: false };
  const buildables = env.runner.playerBuildables(me.id()).map((b) => ({
    type: b.type, cost: num(b.cost), canBuildSomewhere: b.canBuild !== false, canUpgrade: b.canUpgrade,
  }));
  return {
    alive: true, buildables,
    canEmbargoAll: me.canEmbargoAll(),
    allianceTargets: env.game.players().filter((p) => p !== me && p.isAlive() && me.canSendAllianceRequest(p)).map((p) => p.id()),
  };
}

/** Légalité d'une action précise sur une tuile (requête moteur exacte). */
export function legalAt(env: OFEnv, agentIdx: number, tile: number, units?: UnitType[]) {
  const me = playerOf(env, agentIdx)!;
  const m = env.game.map();
  const a = env.runner.playerActions(me.id(), m.x(tile), m.y(tile), units as any);
  return { canAttack: a.canAttack, build: a.buildableUnits.filter((b) => b.canBuild !== false).map((b) => ({ type: b.type, cost: num(b.cost), tile: b.canBuild })), interaction: a.interaction ?? null };
}

import { getSpawnTiles } from "@openfront/engine/execution/Util";
/** Tuiles de spawn légales (échantillonnées) : au moins `minTiles` tuiles valides dans le rayon moteur. */
export function spawnCandidates(env: OFEnv, stride = 12, minTiles = 40): number[] {
  const m = env.game.map(), out: number[] = [];
  for (let y = 0; y < m.height(); y += stride) for (let x = 0; x < m.width(); x += stride) {
    const r = m.ref(x, y);
    if (m.isLand(r) && getSpawnTiles(m, r, false).length >= minTiles) out.push(r);
  }
  return out;
}

/** Tuiles légales (vérifiées par le moteur) pour construire `unit`, parmi un échantillon régulier de tuiles possédées. APPROXIMATION de placement : le choix final est scripté (v1). */
export function buildTiles(env: OFEnv, agentIdx: number, unit: UnitType, maxTiles = 6, maxProbe = 60): number[] {
  const me = playerOf(env, agentIdx); if (!me) return [];
  const tiles = [...me.tiles()]; if (!tiles.length) return [];
  const step = Math.max(1, Math.floor(tiles.length / maxProbe)), out: number[] = [], m = env.game.map();
  for (let i = (env.tick % step); i < tiles.length && out.length < maxTiles; i += step) {
    const a = env.runner.playerActions(me.id(), m.x(tiles[i]), m.y(tiles[i]), [unit as any]);
    const b = a.buildableUnits.find((u) => u.type === (unit as any));
    if (b && b.canBuild !== false) out.push(b.canBuild as number);
  }
  return out;
}
