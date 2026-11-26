// Test d'auto-cohérence : restore(snapshot) + mêmes actions => même hash final.
import { OFEnv, agentId } from "../env.mts";
import { getSpawnTiles } from "@openfront/engine/execution/Util";

const env = new OFEnv();
await env.reset({ map: "World", seed: "selftest01", agents: 2, bots: 50 });
const g = env.game, m = g.map();

// Spawn déterministe des agents sur des tuiles terrestres (pas encore appris : script de test).
const land: number[] = [];
for (let y = 0; y < m.height(); y += 7) for (let x = 0; x < m.width(); x += 7) {
  const r = m.ref(x, y); if (m.isLand(r) && getSpawnTiles(m, r, false).length >= 40) land.push(r);
}
const spawnIntents = [0, 1].map((i) => ({ type: "spawn", tile: land[Math.floor(land.length * (i + 1) / 3)], clientID: agentId(i) }));
let ok = env.stepTick(spawnIntents as any);
while (ok && g.inSpawnPhase()) ok = env.stepTick();
if (!ok) throw new Error("erreur moteur pendant spawn: " + env.error);

const owned = () => [0, 1].map((i) => env.game.players().find((p) => p.name() === `Agent${i}`)?.numTilesOwned() ?? 0);
const afterSpawn = owned();
if (afterSpawn.some((n) => n === 0)) throw new Error("un agent n'a pas spawn: " + afterSpawn);
const T0 = 150, T1 = 450;
const script = (t: number) => (t % 40 === 0)
  ? [{ type: "attack", targetID: null, troops: 50, clientID: agentId(t % 80 === 0 ? 0 : 1) }] : [];

for (let i = 0; i < T0; i++) env.stepTick(script(i) as any);
const snapTick = env.tick, snap = env.snapshot();
for (let i = T0; i < T1; i++) env.stepTick(script(i) as any);
const hashA = env.lastHash?.hash, tickA = env.tick, tilesA = owned();

await env.restore(snap);
if (env.tick !== snapTick) throw new Error(`tick restauré ${env.tick} != ${snapTick}`);
for (let i = T0; i < T1; i++) env.stepTick(script(i) as any);
const hashB = env.lastHash?.hash, tickB = env.tick, tilesB = owned();

console.log(JSON.stringify({ afterSpawn, snapBytes: snap.length, tickA, tickB, hashA: String(hashA), hashB: String(hashB), tilesA, tilesB, identical: hashA === hashB && tickA === tickB, error: env.error ?? null }));
process.exit(hashA === hashB && tickA === tickB && hashA !== undefined ? 0 : 1);
