"""Joue des parties completes avec Teacher2 et rapporte : victoire (>80 % des terres), territoire max, stagnations, actions emises."""
import sys, time, json, pathlib, argparse, random, multiprocessing as mp
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ofsi.client import OFEnvProc
from ofsi.teacher2 import Teacher2
from ofsi.stagnation import StagnationDetector


def play(spec):
    t0 = time.time(); e = OFEnvProc()
    try:
        r = e.reset(map=spec["map"], seed=spec["seed"], agents=1, bots=spec["bots"], difficulty=spec["difficulty"]); cid = r["agentIds"][0]
        c = e.spawn_candidates(); sizes, of = e.landmasses(c)
        order = sorted(range(len(sizes)), key=lambda i: -sizes[i])
        pool = [t for t, m in zip(c, of) if m == order[0]] or c            # spawn sur la plus grande masse (choix du professeur)
        tile = random.Random(spec["seed"]).choice(pool)
        s = e.step_state(1, [{"type": "spawn", "tile": tile, "clientID": cid}])
        while s["state"]["spawnPhase"]: s = e.step_state(1)
        T = Teacher2(cid, e, seed=1, p=spec.get("params")); det = StagnationDetector(); peak = 0; land = None; flagsum = {}; track = []
        de = spec.get("decide_every", 20); end = "max_ticks"
        while s["tick"] < spec.get("max_ticks", 40000):
            st, costs = s["state"], s["costs"]
            if "self" not in st or not st["self"]["alive"]: end = "dead"; break
            if land is None:
                m = e.landmasses(); land = sum(m[0])
            peak = max(peak, st["self"]["tiles"]); fl = det.update(st, costs)
            for k, v in fl.items(): flagsum[k] = flagsum.get(k, 0) + int(bool(v))
            if s["tick"] % 2000 < de: track.append((s["tick"], round(st["self"]["tiles"] / land * 100, 1), st["self"]["gold"], st["self"]["troops"]))
            s = e.step_state(de, T.act(st, costs, s["tick"]))
            if s.get("winner") is not None: end = "winner"; break
            if not s["ok"]: end = "engine_error"; break
        st = s["state"]; me = st.get("self", {})
        win = s.get("winner") is not None and me.get("id") == s.get("winner")
        return {"spec": spec, "end": end, "win": bool(win), "tick": s["tick"], "final_share": round(me.get("tiles", 0) / land * 100, 1) if land else None, "peak_share": round(peak / land * 100, 1) if land else None,
                "land": land, "stagnation_flag_counts": flagsum, "actions": T.log, "track": track, "wall_s": round(time.time() - t0, 1)}
    except Exception as ex:
        return {"spec": spec, "end": "exception", "error": repr(ex)[:300], "win": False}
    finally:
        e.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--maps", default="Onion"); ap.add_argument("--games", type=int, default=2); ap.add_argument("--bots", type=int, default=8)
    ap.add_argument("--difficulty", default="Easy"); ap.add_argument("--workers", type=int, default=8); ap.add_argument("--out", default="benchmarks/teacher2.json"); ap.add_argument("--max-ticks", type=int, default=40000)
    ap.add_argument("--params", default="{}")
    a = ap.parse_args(); specs = [dict(map=m, seed=f"t2{g:05d}{i}", bots=a.bots, difficulty=a.difficulty, max_ticks=a.max_ticks, params=json.loads(a.params)) for i, m in enumerate(a.maps.split(",")) for g in range(a.games)]
    with mp.Pool(a.workers) as pool: res = pool.map(play, specs, chunksize=1)
    pathlib.Path(a.out).write_text(json.dumps(res, indent=1), encoding="utf-8")
    for r in res:
        print(f"{r['spec']['map']:16s} {r['spec']['seed']} {r['end']:11s} win={r['win']!s:5} tick={r.get('tick')} final={r.get('final_share')}% peak={r.get('peak_share')}% flags={r.get('stagnation_flag_counts')} actions={r.get('actions')} {r.get('error','')}")
    print("victoires:", sum(r["win"] for r in res), "/", len(res))
