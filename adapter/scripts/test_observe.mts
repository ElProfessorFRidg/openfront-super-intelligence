import { OFEnv, agentId } from "../env.mts";
import { observe, legalSummary, legalAt, ownerGrid } from "../observe.mts";
import { getSpawnTiles } from "@openfront/engine/execution/Util";
const env = new OFEnv();
await env.reset({ map: "World", seed: "obstest01", agents: 2, bots: 50 });
const m = env.game.map(); const land: number[] = [];
for (let y = 0; y < m.height(); y += 7) for (let x = 0; x < m.width(); x += 7) { const r = m.ref(x, y); if (m.isLand(r) && getSpawnTiles(m, r, false).length >= 40) land.push(r); }
env.stepTick([0, 1].map((i) => ({ type: "spawn", tile: land[Math.floor(land.length * (i + 1) / 3)], clientID: agentId(i) })) as any);
while (env.game.inSpawnPhase()) env.stepTick();
for (let i = 0; i < 400; i++) env.stepTick();
const o: any = observe(env, 0, { grid: true });
const t0 = performance.now(); for (let i = 0; i < 20; i++) observe(env, 0, { grid: true }); const dt = (performance.now() - t0) / 20;
console.log("self:", JSON.stringify(o.self)); console.log("others:", o.others.length, "grid:", o.grid.w + "x" + o.grid.h, "obs ms (grid):", dt.toFixed(1));
console.log("legal:", JSON.stringify(legalSummary(env, 0)));
const me: any = env.game.players().find((p) => p.clientID() === agentId(0))!;
const bt = [...me.borderTiles()][0]; console.log("legalAt border tile:", JSON.stringify(legalAt(env, 0, bt)));
