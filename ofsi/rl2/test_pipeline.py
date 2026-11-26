"""Valide le pipeline v2 de bout en bout : TeacherV2 joue via observations/masques/decodage v2 ; mesure victoires, debit, actions utilisees, illegalites."""
import sys, time, json, pathlib, argparse, collections
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import numpy as np
from ofsi.rl2.vecenv2 import VecEnv2
from ofsi.rl2.teacher_v2 import TeacherV2
from ofsi.rl2 import space as S

ap = argparse.ArgumentParser()
ap.add_argument("--maps", default="Onion"); ap.add_argument("--envs", type=int, default=8); ap.add_argument("--games", type=int, default=8)
ap.add_argument("--bots", type=int, default=8); ap.add_argument("--difficulty", default="Easy"); ap.add_argument("--max-steps", type=int, default=1500)
a = ap.parse_args(); maps = a.maps.split(","); cnt = [0]


def cfg():
    cnt[0] += 1; return {"map": maps[cnt[0] % len(maps)], "bots": a.bots, "difficulty": a.difficulty}


env = VecEnv2(a.envs, cfg, max_steps=a.max_steps); teachers = [TeacherV2(seed=i) for i in range(a.envs)]
t0 = time.time(); decisions = 0; finished = []; used = collections.Counter(); wasted = 0; exec_total = 0
while len(finished) < a.games:
    acts = []
    for i in range(a.envs):
        o = env.obs[i]; sess = env.sess[i]
        if o is None: acts.append([]); continue
        st, costs, cands = sess.cur
        A = teachers[i].act(o, st, costs, cands); acts.append(A)
        for t, p, par in A:
            used[S.TYPES[t]] += 1; exec_total += 1
            if not o["type_mask"][t] or (t not in S.NO_PTR and not o["ptr_mask"][t, p]): wasted += 1       # ne doit JAMAIS arriver (masques exacts)
    rew, done, info = env.step(acts); decisions += a.envs
    for i, inf in enumerate(info):
        if inf:
            finished.append(inf); teachers[i] = TeacherV2(seed=len(finished) + 100)
            print(f"  fin {inf['cfg']['map']:12s} {inf['end']:18s} steps={inf['steps']:4d} tick={inf['tick']} progress={inf['progress']:.2f} ret={inf['ret']:.2f}", flush=True)
dt = time.time() - t0; wins = sum(f["win"] for f in finished)
print(json.dumps({"parties": len(finished), "victoires": wins, "decisions": decisions, "decisions_par_s": round(decisions / dt, 1), "secondes": round(dt),
                  "actions_illegales_selon_masque": wasted, "actions_emises": exec_total, "types_utilises": dict(used.most_common())}, ensure_ascii=False, indent=1))
env.close()
