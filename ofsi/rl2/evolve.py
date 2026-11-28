"""Evolution (1+lambda) des parametres du professeur scripte (MISSION §33). Protocole : docs/JOURNAL.md 2026-11-27. Reprenable (runs/_evolve/gens.jsonl).
Usage : python ofsi/rl2/evolve.py --gens 6 --lam 5 --workers 4  |  python ofsi/rl2/evolve.py --final   (test final sur parties jamais vues)"""
import sys, os, json, time, random, pathlib, argparse, math
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import multiprocessing as mp
from ofsi.rl2.eval_planner import play
from ofsi.rl2.eval2 import make_specs, TRAIN_MAPS, HELDOUT_MAPS
from ofsi.rl2.compare_eval import mcnemar

ROOT = pathlib.Path(__file__).resolve().parents[2]; ED = pathlib.Path(os.environ.get("OFSI_EVOLVE", ROOT / "runs" / "_evolve")); ED.mkdir(parents=True, exist_ok=True)
BASE = {"ratio": 1.5, "reserve": 0.3, "send": 3, "expand": 2, "defend": 0.5, "ally_ratio": 0.6, "city_per_tiles": 3500, "ally_mode": "threats"}
SPACE = {"ratio": (0.8, 3.0, "f"), "reserve": (0.05, 0.6, "f"), "send": (1, 4, "i"), "expand": (1, 4, "i"), "defend": (0.2, 1.0, "f"), "ally_ratio": (0.2, 1.0, "f"), "city_per_tiles": (1500, 7000, "i")}


def mutate(p, rng, sigma=0.15):
    q = dict(p)
    for k, (lo, hi, t) in SPACE.items():
        if rng.random() < 0.5:
            v = q[k] + rng.gauss(0, sigma * (hi - lo)); v = min(hi, max(lo, v)); q[k] = int(round(v)) if t == "i" else round(v, 3)
    if rng.random() < 0.15: q["ally_mode"] = "all" if q["ally_mode"] == "threats" else "threats"
    return q


def fitness(res):
    n = len(res); return sum(r["win"] for r in res) / n + 0.25 * sum(r["progress"] for r in res) / n


def evaluate(cands, specs, workers):
    """cands : liste de dicts de parametres ; retourne, par candidat, la liste des resultats (memes parties pour tous : nombres aleatoires communs)."""
    jobs = [(ci, s) for ci in range(len(cands)) for s in specs]; out = {ci: [] for ci in range(len(cands))}
    with mp.Pool(workers) as pool:
        for ci, r in pool.imap_unordered(_run, [(ci, s, cands[ci]) for ci, s in jobs], chunksize=1): out[ci].append(r)
    return out


def _run(job):
    ci, s, params = job; return ci, play((s, "teacher", params, {}, 1500))


def search(a):
    rng = random.Random(a.seed); gl = ED / "gens.jsonl"; hist = [json.loads(l) for l in open(gl)] if gl.exists() else []; parent = hist[-1]["parent_after"] if hist else dict(BASE)
    for g in range(len(hist), a.gens):
        if (ED / "STOP").exists(): print("STOP"); break
        specs = make_specs(TRAIN_MAPS + HELDOUT_MAPS, ["Medium"], [8, 12], a.per, a.seed0 + 1000 * g); kids = [mutate(parent, rng) for _ in range(a.lam)]; cands = [parent] + kids; t0 = time.time()
        res = evaluate(cands, specs, a.workers); fits = [fitness(res[i]) for i in range(len(cands))]; wins = [sum(r["win"] for r in res[i]) for i in range(len(cands))]
        best = max(range(len(cands)), key=lambda i: (fits[i], -i)); new_parent = cands[best] if fits[best] > fits[0] else parent; conf = None
        if a.confirm and new_parent is not parent:                 # CONFIRMATION : le meilleur enfant doit battre le parent sur des parties NEUVES (strictement plus de victoires), sinon on garde le parent
            cspecs = make_specs(TRAIN_MAPS + HELDOUT_MAPS, ["Medium"], [8, 12], a.per, a.confirm_seed0 + 1000 * g); cr = evaluate([parent, new_parent], cspecs, a.workers)
            cw = [sum(r["win"] for r in cr[i]) for i in (0, 1)]; conf = {"parent": cw[0], "enfant": cw[1]}
            if not cw[1] > cw[0]: new_parent = parent
        rec = {"gen": g, "confirmation": conf, "parent_before": parent, "fits": [round(f, 3) for f in fits], "wins": wins, "best_idx": best, "replaced": new_parent is not parent, "enfant_candidat": cands[best], "parent_after": new_parent, "secondes": round(time.time() - t0)}
        open(gl, "a", encoding="utf-8").write(json.dumps(rec) + "\n"); print(f"gen {g}: victoires {wins} fitness {rec['fits']} -> {'REMPLACE' if rec['replaced'] else 'parent conserve'} ({rec['secondes']} s)", flush=True); parent = new_parent
    return parent


def final(a):
    gl = ED / "gens.jsonl"; best = [json.loads(l) for l in open(gl)][-1]["parent_after"]; specs = make_specs(TRAIN_MAPS + HELDOUT_MAPS, ["Medium"], [8, 12], a.final_per, a.final_seed0)
    res = evaluate([dict(BASE), best], specs, a.workers); W = [{r["cfg"]["_id"]: bool(r["win"]) for r in res[i]} for i in (0, 1)]; ids = sorted(W[0]); b = sum(1 for i in ids if W[1][i] and not W[0][i]); c = sum(1 for i in ids if W[0][i] and not W[1][i])
    rep = {"n": len(ids), "defaut": sum(W[0].values()), "evolue": sum(W[1].values()), "evolue_seul": b, "defaut_seul": c, "p": mcnemar(b, c), "params_defaut": BASE, "params_evolue": best, "morts": [sum(r["end"] == "dead" for r in res[i]) for i in (0, 1)]}
    (ED / "final.json").write_text(json.dumps(rep, indent=1), encoding="utf-8"); (ROOT / "benchmarks" / f"{a.out_name}.json").write_text(json.dumps(rep, indent=1), encoding="utf-8"); print(json.dumps(rep, indent=1)); return rep


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--gens", type=int, default=6); ap.add_argument("--lam", type=int, default=5); ap.add_argument("--workers", type=int, default=4); ap.add_argument("--seed", type=int, default=0); ap.add_argument("--final", action="store_true"); ap.add_argument("--per", type=int, default=2); ap.add_argument("--seed0", type=int, default=2_000_000); ap.add_argument("--confirm", action="store_true"); ap.add_argument("--confirm-seed0", type=int, default=30_000_000); ap.add_argument("--final-per", type=int, default=4); ap.add_argument("--final-seed0", type=int, default=3_000_000); ap.add_argument("--out-name", default="evolve_final"); a = ap.parse_args()
    final(a) if a.final else search(a)
