// stdout est reserve au protocole JSON-lines. Le moteur peut imprimer n'importe quoi (console.info, console.table, process.stdout.write...) : tout est redirige vers stderr,
// et le protocole ecrit via PROTO_WRITE (ecriture reelle sur stdout capturee AVANT la redirection).
const PROTO_WRITE = process.stdout.write.bind(process.stdout);
for (const m of ["log", "info", "debug", "table", "dir", "trace", "group", "groupEnd"] as const) (console as any)[m] = (...a: unknown[]) => console.error(...a);
(process.stdout as any).write = (chunk: any, ...rest: any[]) => (process.stderr as any).write(chunk, ...rest);
// Démon JSON-lines (stdin/stdout) : un environnement OpenFront headless par processus.
// Requête : {"id":n,"cmd":"reset|step|observe|legal|legal_at|snapshot|restore|result|close", ...}
import readline from "readline";
import { OFEnv, agentId } from "./env.mts";
import { boatCandidates } from "./cands.mts";
import { state2, costs as costs2, buildCands, buildCandsAll, upgradeCands, nukeCands, warshipCands } from "./state2.mts";
import { observe, legalSummary, legalAt, spawnCandidates, buildTiles } from "./observe.mts";

const env = new OFEnv();
const snaps = new Map<number, Uint8Array>(); let snapSeq = 0;
const out = (o: unknown) => PROTO_WRITE(JSON.stringify(o) + "\n");

function result() {
  const g = env.game;
  const players = g.players().map((p) => ({ id: p.id(), clientID: p.clientID(), type: p.type(), alive: p.isAlive(), tiles: p.numTilesOwned(), troops: Math.round(p.troops()), gold: Number(p.gold()) }));
  const winner = (g as any).getWinner?.() ?? null;
  return { tick: env.tick, hash: env.lastHash ? String(env.lastHash.hash) : null, winner: winner && typeof winner === "object" ? (winner.id?.() ?? String(winner)) : winner, players, error: env.error ?? null };
}

const rl = readline.createInterface({ input: process.stdin });
let chain = Promise.resolve();
rl.on("line", (line) => { chain = chain.then(async () => {
  let req: any; try { req = JSON.parse(line); } catch { return out({ ok: false, error: "json invalide" }); }
  try {
    switch (req.cmd) {
      case "reset": await env.reset(req.opts); out({ id: req.id, ok: true, tick: env.tick, spawnPhase: env.game.inSpawnPhase(), mapW: env.game.map().width(), mapH: env.game.map().height(), agentIds: Array.from({ length: req.opts.agents }, (_, i) => agentId(i)) }); break;
      case "step": { // {ticks, intents:[...] appliqués au 1er tick}
        let ok = true; const n = req.ticks ?? 1;
        for (let i = 0; i < n && ok; i++) ok = env.stepTick(i === 0 ? (req.intents ?? []) : []);
        out({ id: req.id, ok, tick: env.tick, spawnPhase: env.game.inSpawnPhase(), error: env.error ?? null }); break; }
      case "step_obs": { // step + observation de tous les agents demandés en un aller-retour
        let ok = true; const n = req.ticks ?? 1;
        for (let i = 0; i < n && ok; i++) ok = env.stepTick(i === 0 ? (req.intents ?? []) : []);
        const w = env.game.getWinner(); const wid = w && typeof (w as any).id === "function" ? (w as any).id() : (w ? String((w as any).name ?? "team") : null);
        out({ id: req.id, ok, tick: env.tick, spawnPhase: env.game.inSpawnPhase(), error: env.error ?? null, winner: wid,
              obs: (req.agents ?? [0]).map((a: number) => observe(env, a, { grid: false, costs: !!req.costs })) }); break; }
      case "build_tiles": out({ id: req.id, ok: true, tiles: buildTiles(env, req.agent, req.unit, req.max ?? 6, req.probe ?? 60) }); break;
      case "landmasses": { // composantes connexes de terre (4-voisinage) : tailles et appartenance d'une tuile
        const m = env.game.map(), W = m.width(), H = m.height(), comp = new Int32Array(W * H).fill(-1); const sizes: number[] = [];
        for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
          const r = m.ref(x, y); if (!m.isLand(r) || comp[y * W + x] >= 0) continue;
          const id = sizes.length; let n = 0; const st = [y * W + x]; comp[y * W + x] = id;
          while (st.length) { const i = st.pop()!; n++; const cx = i % W, cy = (i / W) | 0;
            for (const [dx, dy] of [[1,0],[-1,0],[0,1],[0,-1]]) { const nx = cx + dx, ny = cy + dy; if (nx < 0 || ny < 0 || nx >= W || ny >= H) continue;
              const j = ny * W + nx; if (comp[j] < 0 && m.isLand(m.ref(nx, ny))) { comp[j] = id; st.push(j); } } }
          sizes.push(n); }
        const of = (req.tiles ?? []).map((t: number) => comp[m.y(t) * W + m.x(t)]);
        out({ id: req.id, ok: true, sizes, of }); break; }
      case "cands": { // candidats parametres : kind = boat | ...
        if (req.kind === "boat") out({ id: req.id, ok: true, cands: boatCandidates(env, req.agent ?? 0, req.max ?? 24, req.stride ?? 6) });
        else if (req.kind === "build") out({ id: req.id, ok: true, cands: buildCands(env, req.agent ?? 0, req.unit, req.max ?? 16, req.probe ?? 96) });
        else if (req.kind === "build_all") out({ id: req.id, ok: true, cands: buildCandsAll(env, req.agent ?? 0, req.units, req.max ?? 16, req.probe ?? 160) });
        else if (req.kind === "upgrade") out({ id: req.id, ok: true, cands: upgradeCands(env, req.agent ?? 0) });
        else if (req.kind === "nuke") out({ id: req.id, ok: true, cands: nukeCands(env, req.agent ?? 0, req.unit, req.max ?? 16) });
        else if (req.kind === "warship") out({ id: req.id, ok: true, cands: warshipCands(env, req.agent ?? 0, req.max ?? 8) });
        else out({ id: req.id, ok: false, error: "kind inconnu: " + req.kind }); break; }
      case "state2": out({ id: req.id, ok: true, state: state2(env, req.agent ?? 0, { maxPlayers: req.maxPlayers }), costs: costs2(env, req.agent ?? 0) }); break;
      case "step_state": { // step + etat riche (un aller-retour)
        let ok = true; const n = req.ticks ?? 1; for (let i = 0; i < n && ok; i++) ok = env.stepTick(i === 0 ? (req.intents ?? []) : []);
        const w = env.game.getWinner(); const wid = w && typeof (w as any).id === "function" ? (w as any).id() : (w ? String((w as any).name ?? "team") : null);
        out({ id: req.id, ok, tick: env.tick, error: env.error ?? null, winner: wid, state: state2(env, req.agent ?? 0, { maxPlayers: req.maxPlayers }), costs: costs2(env, req.agent ?? 0) }); break; }
      case "replay_view": {
        const g = env.game, map = g.map(), width = map.width(), height = map.height();
        const size = Math.max(40, Math.min(240, Number(req.size) || 160));
        const block = Math.ceil(Math.max(width, height) / size);
        const gw = Math.ceil(width / block), gh = Math.ceil(height / block);
        const buildings = new Set(["City", "Port", "Defense Post", "Factory", "SAM Launcher", "Missile Silo", "Warship", "Transport", "Trade Ship", "Train", "Atom Bomb", "Hydrogen Bomb", "MIRV", "MIRV Warhead", "SAMMissile", "Shell"]);
        const players = [], units = [], stats = [], counts = new Map<number, number>();
        let self = null;
        const replayPlayers = g.players();
        const viewer = replayPlayers.find(p => p.clientID() === agentId(req.agent ?? 0));
        for (const p of replayPlayers) {
          const code = p.smallID() + 2;
          players.push([code, p.name()]);
          stats.push([code, p.name(), p.numTilesOwned(), Math.round(p.troops()), Number(p.gold()),
                      p.isAlive(), Boolean(viewer && viewer !== p && viewer.isAlliedWith(p)), p.id()]);
          if (p.clientID() === agentId(req.agent ?? 0)) self = code;
          for (const unit of p.units()) {
            if (!unit.isActive() || !buildings.has(unit.type())) continue;
            units.push([code, unit.type(), map.x(unit.tile()), map.y(unit.tile()), unit.level()]);
          }
        }
        const runs = Buffer.allocUnsafe(gw * gh * 4);
        let last = -1, length = 0, offset = 0;
        function flush() {
          if (!length) return;
          runs.writeUInt16LE(length, offset);
          runs.writeUInt16LE(last, offset + 2);
          offset += 4;
        }
        for (let by = 0; by < gh; by++) {
          for (let bx = 0; bx < gw; bx++) {
            counts.clear();
            let samples = 0, land = 0, owner = 1, high = 0;
            for (let y = by * block; y < Math.min(height, (by + 1) * block); y += 2) {
              for (let x = bx * block; x < Math.min(width, (bx + 1) * block); x += 2) {
                samples++;
                const tile = map.ref(x, y);
                if (!map.isLand(tile)) continue;
                land++;
                if (!map.hasOwner(tile)) continue;
                const code = map.ownerID(tile) + 2;
                const count = (counts.get(code) ?? 0) + 1;
                counts.set(code, count);
                if (count > high) { high = count; owner = code; }
              }
            }
            const code = high > 0 && high * 4 >= land ? owner : land * 4 >= samples ? 1 : 0;
            if (code === last && length < 65535) length++;
            else { flush(); last = code; length = 1; }
          }
        }
        flush();
        out({ id: req.id, ok: true, gw, gh, width, height, self, players, units, stats,
              owners: runs.subarray(0, offset).toString("base64") });
        break;
      }
      case "grid2": { // vue geographique grossiere (<=32x32) : par cellule, fractions terre / moi / allie / ennemi (echantillon 1/2)
        const me = (await import("./observe.mts")).playerOf(env, req.agent ?? 0); const m = env.game.map(), W = m.width(), H = m.height();
        const blk = Math.max(1, Math.ceil(Math.max(W, H) / (req.size ?? 32))), gw = Math.ceil(W / blk), gh = Math.ceil(H / blk);
        const data = new Float32Array(gw * gh * 4); const allies = new Set(me ? me.allies().map((a) => a.smallID()) : []);
        for (let by = 0; by < gh; by++) for (let bx = 0; bx < gw; bx++) {
          let n = 0, land = 0, mine = 0, ally = 0, foe = 0;
          for (let y = by * blk; y < Math.min(H, (by + 1) * blk); y += 2) for (let x = bx * blk; x < Math.min(W, (bx + 1) * blk); x += 2) {
            const r = m.ref(x, y); n++; if (!m.isLand(r)) continue; land++;
            if (m.hasOwner(r)) { const o = m.ownerID(r); if (me && o === me.smallID()) mine++; else if (allies.has(o)) ally++; else foe++; }
          }
          const i = (by * gw + bx) * 4; data[i] = n ? land / n : 0; data[i + 1] = n ? mine / n : 0; data[i + 2] = n ? ally / n : 0; data[i + 3] = n ? foe / n : 0;
        }
        out({ id: req.id, ok: true, gw, gh, blk, data: Array.from(data, (v) => Math.round(v * 100) / 100) }); break; }
      case "selftest_noise": { // provoque du bruit sur stdout (regression : AllianceExtensionExecution.console.info)
        console.info("[AllianceExtensionExecution] Player x or y is not alive"); console.table({ a: 1 }); process.stdout.write("[bruit direct]\n"); out({ id: req.id, ok: true, noise_sent: 3 }); break; }
      case "observe": out({ id: req.id, ok: true, obs: observe(env, req.agent, { grid: !!req.grid }) }); break;
      case "legal": out({ id: req.id, ok: true, legal: legalSummary(env, req.agent) }); break;
      case "legal_at": out({ id: req.id, ok: true, legal: legalAt(env, req.agent, req.tile, req.units) }); break;
      case "spawn_candidates": out({ id: req.id, ok: true, tiles: spawnCandidates(env, req.stride ?? 12, req.minTiles ?? 40) }); break;
      case "snapshot": { const s = env.snapshot(); const k = ++snapSeq; snaps.set(k, s); out({ id: req.id, ok: true, snap: k, bytes: s.length }); break; }
      case "restore": { await env.restore(snaps.get(req.snap)!); out({ id: req.id, ok: true, tick: env.tick }); break; }
      case "result": out({ id: req.id, ok: true, result: result() }); break;
      case "close": out({ id: req.id, ok: true }); process.exit(0);
      default: out({ id: req.id, ok: false, error: "cmd inconnue: " + req.cmd });
    }
  } catch (e: any) { out({ id: req.id, ok: false, error: String(e?.stack ?? e) }); }
}); });
