"""Evaluation APPARIEE professeur seul vs professeur+planificateur : memes parties (cartes/difficulte/bots/graine du jeu), meme graine de professeur par partie, meme code d'execution.
Usage : python ofsi/rl2/eval_planner.py --arm teacher|planner --params '{"ally_mode":"threats"}' --difficulty Medium --out benchmarks/plan_x.json"""
import sys, json, time, pathlib, argparse
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import multiprocessing as mp
from ofsi.rl2.env2 import Session
from ofsi.rl2.teacher_v2 import TeacherV2
from ofsi.rl2.planner import Planner, PlannerAbort
from ofsi.rl2.vecenv2 import potential
from ofsi.rl2.eval2 import make_specs, summarize, TRAIN_MAPS, HELDOUT_MAPS


def play(job):
    try: return _play(job)
    except Exception as e:                                     # une partie en erreur ne doit JAMAIS faire perdre les autres : enregistrement explicite, exclue du decompte des victoires
        return {"cfg": job[0], "end": "engine_error" if not isinstance(e, PlannerAbort) else "planner_abort", "win": False, "progress": 0.0, "steps": 0, "tick": 0, "secondes": 0, "error": str(e)[:300], "plans": 0, "switches": 0, "chosen": {}}


def _play(job):
    spec, arm, params, pl, max_steps = job; sess = Session(20, max_steps); t0 = time.time()
    cfg = {k: v for k, v in spec.items()}; obs = sess.start(cfg, spec["_seed"]); te = TeacherV2(seed=spec["_id"], **params); planner = Planner(params, **pl) if arm == "planner" else None
    steps, end, win, pot, tick = 0, None, False, 0.0, 0
    while steps < max_steps:
        if obs is None: end = "dead"; break
        st, costs, cands = sess.cur; was_spawn = bool(st.get("spawnPhase")); acts = te.act(obs, st, costs, cands)
        if planner is not None: acts = planner.choose(sess, obs, acts, steps)
        r = sess.apply(acts); steps += 1; st = r["state"]
        if was_spawn:
            sess.spawn_wait(); st = sess.last["state"]; r = sess.last
            if "self" not in st: end = "spawn_failed"; break
        alive = "self" in st and st["self"]["alive"]; wid = r.get("winner"); me = st["self"]["id"] if "self" in st else None; tick = r.get("tick", 0)
        pot = potential(st) if not st.get("spawnPhase") else 0.0
        if wid is not None: win = (wid == me); end = "win" if win else "loss_winner_other"; break
        if not alive and not st.get("spawnPhase"): end = "dead"; break
        obs = sess.observe()
    sess.close(); end = end or "timeout"
    return {"cfg": cfg, "end": end, "win": win, "progress": pot, "steps": steps, "tick": tick, "secondes": round(time.time() - t0, 1),
            "snap_invalid": getattr(planner, "n_snap_invalid", 0), "plans": getattr(planner, "n_plans", 0), "switches": getattr(planner, "n_switch", 0), "chosen": getattr(planner, "chosen", {})}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--arm", choices=["teacher", "planner"], required=True); ap.add_argument("--params", default='{"ally_mode":"threats"}'); ap.add_argument("--difficulty", default="Medium")
    ap.add_argument("--per", type=int, default=2); ap.add_argument("--bots", default="8,12"); ap.add_argument("--seed0", type=int, default=1000000); ap.add_argument("--workers", type=int, default=3); ap.add_argument("--max-steps", type=int, default=1500)
    ap.add_argument("--H", type=int, default=30); ap.add_argument("--every", type=int, default=4); ap.add_argument("--margin", type=float, default=0.05); ap.add_argument("--only-ids", default=""); ap.add_argument("--out", required=True)
    a = ap.parse_args(); specs = make_specs(TRAIN_MAPS + HELDOUT_MAPS, a.difficulty.split(","), [int(x) for x in a.bots.split(",")], a.per, a.seed0)
    if a.only_ids: keep = {int(x) for x in a.only_ids.split(",")}; specs = [s for s in specs if s["_id"] in keep]
    params = json.loads(a.params); pl = dict(H=a.H, every=a.every, margin=a.margin); t0 = time.time()
    part = pathlib.Path(a.out + ".partial.jsonl"); res = []
    if part.exists(): res = [json.loads(l) for l in part.read_text(encoding="utf-8").splitlines() if l.strip()]               # REPRISE : parties deja terminees
    done = {r["cfg"]["_id"] for r in res}; todo = [s for s in specs if s["_id"] not in done]; print(f"deja faites: {len(done)} ; a jouer: {len(todo)}", flush=True)
    with mp.Pool(a.workers) as pool:
        for r in pool.imap_unordered(play, [(s, a.arm, params, pl, a.max_steps) for s in todo], chunksize=1):
            res.append(r); part.open("a", encoding="utf-8").write(json.dumps(r) + "\n"); print(f"[{len(res)}/{len(specs)}] id={r['cfg']['_id']} {r['end']} win={r['win']} ({r['secondes']} s)", flush=True)
    summ = summarize(res); rep = {"arm": a.arm, "params": params, "planner": pl if a.arm == "planner" else None, "specs": len(specs), "secondes": round(time.time() - t0), "resume": summ, "parties": res}
    pathlib.Path(a.out).write_text(json.dumps(rep, indent=1), encoding="utf-8")
    for d, v in summ["TOUT"].items(): print(f"{a.arm} {d:8s} {v['victoires']}/{v['parties']} = {v['taux']:.2f} IC95 {v['ic95']} morts {v['morts']} timeouts {v['timeouts']}")
    print("secondes:", rep["secondes"])
