"""Débit agrégé du moteur headless vs nombre d'environnements (processus Node indépendants). Mesure réelle, pas d'extrapolation."""
import sys, time, json, platform, threading, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ofsi.client import OFEnvProc

def worker(i, ticks, res, barrier, map_name, bots):
    e = OFEnvProc()
    r = e.reset(map=map_name, seed=f"bench{i:04d}x", agents=2, bots=bots)
    c = e.spawn_candidates(); sp = [{"type": "spawn", "tile": c[len(c) * (k + 1) // 3], "clientID": r["agentIds"][k]} for k in range(2)]
    s = e.step(1, sp)
    while s["spawnPhase"]: s = e.step(1)
    barrier.wait()  # départ simultané de la mesure
    t = time.perf_counter(); done = 0
    while done < ticks:
        s = e.step(25); done += 25
        if not s["ok"]: break
    dt = time.perf_counter() - t
    res[i] = {"ticks": done, "sec": dt, "ok": s["ok"]}
    e.close()

def run(n, ticks, map_name, bots):
    res = {}; b = threading.Barrier(n)
    ths = [threading.Thread(target=worker, args=(i, ticks, res, b, map_name, bots)) for i in range(n)]
    [t.start() for t in ths]; [t.join() for t in ths]
    wall = max(r["sec"] for r in res.values()); tot = sum(r["ticks"] for r in res.values())
    return {"envs": n, "ticks_each": ticks, "agg_ticks_per_s": round(tot / wall), "per_env_ticks_per_s": round(tot / wall / n), "all_ok": all(r["ok"] for r in res.values())}

if __name__ == "__main__":
    map_name = sys.argv[1]; bots = int(sys.argv[2]); ticks = int(sys.argv[3]); ns = [int(x) for x in sys.argv[4].split(",")]
    out = {"machine": platform.processor(), "map": map_name, "bots": bots, "ticks": ticks, "runs": []}
    for n in ns:
        r = run(n, ticks, map_name, bots); out["runs"].append(r); print(r, flush=True)
    pathlib.Path("benchmarks").mkdir(exist_ok=True)
    pathlib.Path(f"benchmarks/parallel_{map_name}_{bots}bots.json").write_text(json.dumps(out, indent=1))
