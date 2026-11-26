// Etat riche (observations legitimes) + candidats parametres pour TOUTES les actions de gameplay. Legalite = fonctions exactes du moteur.
import { UnitType } from "@openfront/engine-api/game/GameTypes";
import type { OFEnv } from "./env.mts";
import { playerOf } from "./observe.mts";

const num = (b: bigint | number) => Number(b);
const STRUCT = [UnitType.City, UnitType.Port, UnitType.DefensePost, UnitType.Factory, UnitType.SAMLauncher, UnitType.MissileSilo] as const;
const UPGRADABLE = [UnitType.City, UnitType.Port, UnitType.Factory, UnitType.SAMLauncher, UnitType.MissileSilo] as const;
export const NUKES = [UnitType.AtomBomb, UnitType.HydrogenBomb, UnitType.MIRV] as const;

/** Etat complet de l'agent : ce qu'un joueur humain peut voir/savoir dans l'interface. */
export function state2(env: OFEnv, agentIdx: number, opts: { maxPlayers?: number } = {}) {
  const g = env.game, me = playerOf(env, agentIdx), m = g.map(), W = m.width(), H = m.height();
  if (!me) return { tick: env.tick, spawnPhase: g.inSpawnPhase(), error: "agent introuvable" } as any;
  const cfg = g.config();
  const units = me.units().filter((u) => u.isActive()).map((u) => ({ id: u.id(), type: u.type(), x: m.x(u.tile()), y: m.y(u.tile()), level: u.level(), upgradable: (UPGRADABLE as readonly string[]).includes(u.type()) ? me.canUpgradeUnit(u) : false }));
  const unitCount: Record<string, number> = {}; for (const u of units) unitCount[u.type] = (unitCount[u.type] ?? 0) + 1;
  const out = me.outgoingAttacks().map((a) => ({ id: a.id(), target: a.target().isPlayer() ? (a.target() as any).id() : null, troops: Math.round(a.troops()), retreating: a.retreating() }));
  const inc = me.incomingAttacks().map((a) => ({ from: a.attacker().id(), troops: Math.round(a.troops()), retreating: a.retreating() }));
  const maxT = cfg.maxTroops(me);
  const self = {
    id: me.id(), alive: me.isAlive(), spawned: me.hasSpawned(), immune: me.isImmune(), traitor: me.isTraitor(), decaying: me.isDecaying(),
    gold: num(me.gold()), troops: Math.round(me.troops()), maxTroops: Math.round(maxT), tiles: me.numTilesOwned(), borderTiles: me.borderTiles().size,
    tradeGold: num(me.tradeGold()), trainGold: num(me.trainGold()), piracyGold: num(me.piracyGold()), goldEarned: num(me.goldEarned()),
    allies: me.allies().map((a) => a.id()), targets: me.targets().map((t) => t.id()), tradingPartners: me.tradingPartners().length, canEmbargoAll: me.canEmbargoAll(),
    boatsMax: cfg.boatMaxNumber(), boats: me.unitCount(UnitType.TransportShip), units: unitCount,
    incomingAllianceRequests: me.incomingAllianceRequests().map((r: any) => r.requestor().id()),
  };
  const others = g.players().filter((p) => p !== me && p.isAlive());
  others.sort((a, b) => (Number(me.sharesBorderWith(b)) - Number(me.sharesBorderWith(a))) || (b.numTilesOwned() - a.numTilesOwned()));
  const players = others.slice(0, opts.maxPlayers ?? 24).map((p) => {
    let flags: any = {};
    let ft: number | undefined; for (const t of p.borderTiles()) { ft = t; break; }                       // premier element SANS copier tout l'ensemble de tuiles
    if (ft === undefined) for (const t of p.tiles()) { ft = t; break; }
    const it = ft !== undefined ? env.runner.playerActions(me.id(), m.x(ft), m.y(ft), null).interaction : undefined;
    if (it) flags = it;
    return {
      id: p.id(), type: p.type(), tiles: p.numTilesOwned(), troops: Math.round(p.troops()), relation: me.relation(p), allied: me.isAlliedWith(p), traitor: p.isTraitor(), immune: p.isImmune(),
      theirRelation: p.relation(me), border: me.sharesBorderWith(p), canAttack: me.canAttackPlayer(p), canTrade: me.canTrade(p), embargoedByMe: me.hasEmbargoAgainst(p), embargoesMe: p.hasEmbargoAgainst(me),
      incomingRequest: me.incomingAllianceRequests().some((r: any) => r.requestor() === p), canAlly: me.canSendAllianceRequest(p),
      canEmoji: !!flags.canSendEmoji, canDonateGold: !!flags.canDonateGold, canDonateTroops: !!flags.canDonateTroops, canTarget: !!flags.canTarget, canBreak: !!flags.canBreakAlliance, canEmbargo: !!flags.canEmbargo,
      allianceInfo: flags.allianceInfo ?? null,
    };
  });
  const win = { landTiles: g.numLandTiles() - g.numTilesWithFallout(), thresholdTenths: cfg.percentageTilesOwnedToWinTenths(g.elapsedGameSeconds()), canDeleteUnit: me.canDeleteUnit() };
  return { tick: env.tick, spawnPhase: g.inSpawnPhase(), map: { w: W, h: H }, win, self, units, outgoingAttacks: out, incomingAttacks: inc, players, nOthersAlive: others.length };
}

/** Prix des unites constructibles (gold) + abordabilite. */
export function costs(env: OFEnv, agentIdx: number) {
  const me = playerOf(env, agentIdx); if (!me) return {};
  return Object.fromEntries(env.runner.playerBuildables(me.id()).map((b) => [b.type, num(b.cost)]));
}

/** Tuiles de construction legales pour `unit`, avec caracteristiques (cote, relief, distance frontiere approx.). */
export function buildCands(env: OFEnv, agentIdx: number, unit: UnitType, maxN = 16, probe = 96) {
  const me = playerOf(env, agentIdx); if (!me) return [];
  const m = env.game.map(), W = m.width(), H = m.height(), tiles = [...me.tiles()]; if (!tiles.length) return [];
  const step = Math.max(1, Math.floor(tiles.length / probe)), out: any[] = [], seen = new Set<number>();
  for (let i = (env.tick % step); i < tiles.length && out.length < maxN; i += step) {
    const t = tiles[i], a = env.runner.playerActions(me.id(), m.x(t), m.y(t), [unit as any]);
    const b = a.buildableUnits.find((u) => u.type === (unit as any)); if (!b || b.canBuild === false) continue;
    const c = b.canBuild as number; if (seen.has(c)) continue; seen.add(c);
    out.push({ tile: c, x: m.x(c) / W, y: m.y(c) / H, shore: m.isShore(c), mag: m.magnitude(c) / 31, border: m.isBorder(c), railOverlap: (b.overlappingRailroads?.length ?? 0) > 0, cost: num(b.cost) });
  }
  return out;
}

/** Ameliorations legales : unites propres ameliorables avec cout exact (cumule pour amount=1..). */
export function upgradeCands(env: OFEnv, agentIdx: number) {
  const me = playerOf(env, agentIdx); if (!me) return [];
  const m = env.game.map(), out: any[] = [];
  for (const u of me.units()) {
    if (!u.isActive() || !(UPGRADABLE as readonly string[]).includes(u.type()) || !me.canUpgradeUnit(u)) continue;
    const a = env.runner.playerActions(me.id(), m.x(u.tile()), m.y(u.tile()), [u.type() as any]);
    const b = a.buildableUnits.find((x) => x.type === (u.type() as any));
    out.push({ id: u.id(), type: u.type(), level: u.level(), x: m.x(u.tile()), y: m.y(u.tile()), cost: b?.upgradeCosts ? b.upgradeCosts.map(num) : [] });
  }
  return out;
}

/** Cibles d'arme nucleaire legales (silo a portee selon le moteur) : structures et zones ennemies. */
export function nukeCands(env: OFEnv, agentIdx: number, nuke: UnitType, maxN = 16) {
  const me = playerOf(env, agentIdx); if (!me) return [];
  const m = env.game.map(), W = m.width(), H = m.height(), out: any[] = [], seen = new Set<number>();
  const targets: { t: number; who: any; kind: string }[] = [];
  for (const p of env.game.players()) {
    if (p === me || !p.isAlive() || me.isAlliedWith(p)) continue;
    for (const u of p.units()) if (u.isActive() && (STRUCT as readonly string[]).includes(u.type())) targets.push({ t: u.tile(), who: p, kind: u.type() });
  }
  for (const { t, who, kind } of targets) {
    if (out.length >= maxN) break; if (seen.has(t)) continue; seen.add(t);
    const a = env.runner.playerActions(me.id(), m.x(t), m.y(t), [nuke as any]);
    const b = a.buildableUnits.find((x) => x.type === (nuke as any)); if (!b || b.canBuild === false) continue;
    out.push({ tile: t, x: m.x(t) / W, y: m.y(t) / H, owner: who.id(), ownerTiles: who.numTilesOwned(), kind, cost: num(b.cost) });
  }
  return out;
}

/** Zones de patrouille pour un Warship : eau proche de mes cotes, valide selon le moteur. */
export function warshipCands(env: OFEnv, agentIdx: number, maxN = 8) {
  const me = playerOf(env, agentIdx); if (!me) return [];
  const m = env.game.map(), W = m.width(), H = m.height(), tiles = [...me.borderTiles()].filter((t) => m.isShore(t)); if (!tiles.length) return [];
  const out: any[] = [], step = Math.max(1, Math.floor(tiles.length / 40));
  for (let i = env.tick % step; i < tiles.length && out.length < maxN; i += step) {
    for (const n of m.neighbors(tiles[i])) {
      if (!m.isWater(n)) continue;
      const a = env.runner.playerActions(me.id(), m.x(n), m.y(n), [UnitType.Warship as any]);
      const b = a.buildableUnits.find((x) => x.type === (UnitType.Warship as any));
      if (b && b.canBuild !== false) { out.push({ tile: n, x: m.x(n) / W, y: m.y(n) / H, cost: num(b.cost) }); break; }
    }
  }
  return out;
}


/** Candidats de construction pour PLUSIEURS types en un seul passage (une requete moteur par tuile sondee pour tous les types). */
export function buildCandsAll(env: OFEnv, agentIdx: number, units: UnitType[], maxN = 16, probe = 160) {
  const me = playerOf(env, agentIdx); const res: Record<string, any[]> = Object.fromEntries(units.map((u) => [u, []]));
  if (!me) return res;
  const m = env.game.map(), W = m.width(), H = m.height(), tiles = [...me.tiles()]; if (!tiles.length) return res;
  const step = Math.max(1, Math.floor(tiles.length / probe)), seen: Record<string, Set<number>> = Object.fromEntries(units.map((u) => [u, new Set<number>()]));
  for (let i = (env.tick % step); i < tiles.length; i += step) {
    if (units.every((u) => res[u].length >= maxN)) break;
    const t = tiles[i], a = env.runner.playerActions(me.id(), m.x(t), m.y(t), units as any);
    for (const b of a.buildableUnits) {
      const u = b.type as string; if (!res[u] || res[u].length >= maxN || b.canBuild === false) continue;
      const c = b.canBuild as number; if (seen[u].has(c)) continue; seen[u].add(c);
      res[u].push({ tile: c, x: m.x(c) / W, y: m.y(c) / H, shore: m.isShore(c), mag: m.magnitude(c) / 31, border: m.isBorder(c), railOverlap: (b.overlappingRailroads?.length ?? 0) > 0, cost: num(b.cost) });
    }
  }
  return res;
}
