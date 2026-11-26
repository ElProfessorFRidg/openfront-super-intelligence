// Generation de candidats d'action (cibles legales) validee par les fonctions EXACTES du moteur.
// Une action parametree = type + pointeur vers un candidat ; le masque dynamique = ensemble des candidats legaux.
import type { OFEnv } from "./env.mts";
import { playerOf } from "./observe.mts";
import { canBuildTransportShip } from "@openfront/engine/game/TransportShipUtils";

const COMP = new WeakMap<object, { comp: Int32Array; sizes: number[] }>();

/** Composantes connexes de terre (4-voisinage), cache par partie. */
export function landComp(env: OFEnv) {
  const g = env.game; let c = COMP.get(g as object);
  if (c) return c;
  const m = g.map(), W = m.width(), H = m.height(), comp = new Int32Array(W * H).fill(-1), sizes: number[] = [];
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    if (!m.isLand(m.ref(x, y)) || comp[y * W + x] >= 0) continue;
    const id = sizes.length; let n = 0; const st = [y * W + x]; comp[y * W + x] = id;
    while (st.length) {
      const i = st.pop()!; n++; const cx = i % W, cy = (i / W) | 0;
      for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
        const nx = cx + dx, ny = cy + dy; if (nx < 0 || ny < 0 || nx >= W || ny >= H) continue;
        const j = ny * W + nx; if (comp[j] < 0 && m.isLand(m.ref(nx, ny))) { comp[j] = id; st.push(j); }
      }
    }
    sizes.push(n);
  }
  c = { comp, sizes }; COMP.set(g as object, c); return c;
}

export interface BoatCand { tile: number; x: number; y: number; owner: string | null; ownerType: string | null; landmass: number; landmassSize: number; src: number; ownerTiles: number; ownerTroops: number }

/** Candidats d'invasion navale : tuiles de cote hors de ma terre, legales selon le moteur (canBuildTransportShip), diversifiees par masse/proprietaire. */
export function boatCandidates(env: OFEnv, agentIdx: number, maxN = 24, stride = 6): BoatCand[] {
  const me = playerOf(env, agentIdx); if (!me || !me.isAlive()) return [];
  const g = env.game, m = g.map(), W = m.width(), H = m.height(), { comp, sizes } = landComp(env);
  const groups = new Map<string, BoatCand[]>();
  const off = (env.tick >> 3) % stride;   // decalage deterministe dependant du tick : couvre differentes cotes au fil du temps
  for (let y = off; y < H; y += stride) for (let x = off; x < W; x += stride) {
    const t = m.ref(x, y);
    if (!m.isLand(t) || !m.isShore(t)) continue;
    const ow = g.owner(t); if (ow === me) continue;
    const key = `${comp[y * W + x]}|${ow.isPlayer() ? ow.id() : "n"}`;
    const arr = groups.get(key) ?? []; if (arr.length >= 3) continue;           // au plus 3 essais par (masse, proprietaire)
    const src = canBuildTransportShip(g, me, t); if (src === false) continue;
    const p: any = ow.isPlayer() ? ow : null;
    arr.push({ tile: t, x, y, owner: p ? p.id() : null, ownerType: p ? p.type() : null, landmass: comp[y * W + x], landmassSize: sizes[comp[y * W + x]], src: src as number, ownerTiles: p ? p.numTilesOwned() : 0, ownerTroops: p ? Math.round(p.troops()) : 0 });
    groups.set(key, arr);
  }
  const lists = [...groups.values()].sort((a, b) => b[0].landmassSize - a[0].landmassSize);
  const out: BoatCand[] = [];
  for (let r = 0; out.length < maxN && r < 3; r++) for (const l of lists) { if (l[r] && out.length < maxN) out.push(l[r]); }
  return out;
}
