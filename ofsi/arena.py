"""Arène locale : parties indépendantes en parallèle, résultats réels par difficulté, IC de Wilson. Aucune donnée inventée."""
import sys, json, time, math, pathlib, argparse, multiprocessing as mp
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ofsi.client import OFEnvProc
from ofsi import agents as A

def wilson(k, n, z=1.96):
    if n == 0: return (None, None)
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - r) / d, (c + r) / d)

def run_game(spec):
    """spec: map, seed, bots, nations, difficulty, agent (nom), n_agents, decide_every, max_ticks. Retourne un dict de résultats."""
    t0 = time.time(); e = None
    try:
        e = OFEnvProc(); n = spec.get("n_agents", 1)
        r = e.reset(map=spec["map"], seed=spec["seed"], agents=n, bots=spec["bots"], nations=spec.get("nations", "default"), difficulty=spec["difficulty"])
        cls = getattr(A, spec["agent"]); ag = [cls(i, r["agentIds"][i], rng_seed=sum(map(ord, spec["seed"])) + i, **spec.get("params", {})) for i in range(n)]
        c = e.spawn_candidates(); s = e.step_obs(1, [x for a in ag for x in a.spawn(c)], agents=[a.idx for a in ag], costs=True)
        while s["spawnPhase"]: s = e.step_obs(1, agents=[a.idx for a in ag], costs=True)
        pids = {}; peak = 0; de = spec_de = spec.get("decide_every", 20); mx = spec.get("max_ticks", 30000); tick = s["tick"]; end = "max_ticks"; obs = s["obs"]
        while tick < mx:
            intents = []
            for a, o in zip(ag, obs):
                if "self" in o:
                    pids[a.idx] = o["self"]["id"]; peak = max(peak, o["self"]["tiles"])
                    intents += a.act(tick, o, e)
            s = e.step_obs(de, intents, agents=[a.idx for a in ag], costs=True); tick = s["tick"]; obs = s["obs"]
            if not s["ok"]: end = "engine_error"; break
            if s.get("winner") is not None: end = "winner"; break
        res = e.result(); win = res["winner"]; alive = {p["id"]: p for p in res["players"] if p["alive"]}
        return {"ok": end != "engine_error", "end": end, "ticks": tick, "win": any(pid == win for pid in pids.values()),
                "survived": any(pid in alive for pid in pids.values()), "peak_tiles": peak, "wall_s": round(time.time() - t0, 2), "spec": spec,
                "error": s.get("error") if end == "engine_error" else None}
    except Exception as ex:
        return {"ok": False, "end": "exception", "error": repr(ex)[:300], "spec": spec, "win": False, "survived": False, "ticks": 0, "peak_tiles": 0, "wall_s": round(time.time() - t0, 2)}
    finally:
        if e: e.close()

def summarize(results):
    out = {}
    for d in sorted({r["spec"]["difficulty"] for r in results}):
        rs = [r for r in results if r["spec"]["difficulty"] == d]; valid = [r for r in rs if r["ok"]]
        k = sum(r["win"] for r in valid); n = len(valid); lo, hi = wilson(k, n)
        out[d] = {"games": len(rs), "valid": n, "invalid": len(rs) - n, "wins": k, "win_rate": (k / n if n else None), "ci95": [lo, hi],
                  "survived": sum(r["survived"] for r in valid), "mean_ticks": (sum(r["ticks"] for r in valid) / n if n else None),
                  "mean_peak_tiles": (sum(r["peak_tiles"] for r in valid) / n if n else None)}
    return out

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--agent", default="ExpansionAgent"); ap.add_argument("--map", default="Onion")
    ap.add_argument("--bots", type=int, default=10); ap.add_argument("--games", type=int, default=20); ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--difficulties", default="Easy,Medium,Hard,Impossible"); ap.add_argument("--seed-base", type=int, default=0); ap.add_argument("--tag", default=""); ap.add_argument("--params", default="{}")
    a = ap.parse_args(); specs = []
    for d in a.difficulties.split(","):
        for g in range(a.games):
            specs.append({"map": a.map, "seed": f"ar{a.seed_base + g:06d}", "bots": a.bots, "difficulty": d, "agent": a.agent, "n_agents": 1, "params": json.loads(a.params)})
    t0 = time.time()
    with mp.Pool(a.workers) as pool: results = pool.map(run_game, specs, chunksize=1)
    wall = time.time() - t0; summ = summarize(results)
    rep = {"agent": a.agent, "params": json.loads(a.params), "map": a.map, "bots": a.bots, "wall_s": round(wall, 1), "games_total": len(results), "games_per_hour": round(len(results) / wall * 3600), "summary": summ}
    pathlib.Path("benchmarks").mkdir(exist_ok=True); pathlib.Path(f"benchmarks/arena_{a.agent}_{a.map}{a.tag}.json").write_text(json.dumps({"report": rep, "games": results}, indent=1))
    print(json.dumps(rep, indent=1))
