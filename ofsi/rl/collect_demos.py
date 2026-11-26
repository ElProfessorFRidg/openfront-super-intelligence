"""Collecte de demonstrations du professeur via le meme VecEnv que l'entrainement (distribution coherente)."""
import sys, pathlib, random, argparse, time, numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from ofsi.rl import spec
from ofsi.rl.vecenv import VecEnv
from ofsi.rl.ppo import STAGES
from ofsi.rl.teacher import teacher_action

ap = argparse.ArgumentParser(); ap.add_argument("--envs", type=int, default=16); ap.add_argument("--steps", type=int, default=400); ap.add_argument("--out", default="data/demos_v1.npz"); ap.add_argument("--eps", type=float, default=0.1)
a = ap.parse_args(); rng = random.Random(1); t0 = time.time()
venv = VecEnv(a.envs, lambda: dict(STAGES[rng.randrange(0, 4)], _stage=0), max_steps=1500)
X, M, nbs = venv.featurize(); xs, ms, ts, fs = [], [], [], []; ends = []
for step in range(a.steps):
    at = np.zeros(a.envs, np.int64); af = np.zeros(a.envs, np.int64)
    for i, s in enumerate(venv.slots):
        t, f = teacher_action(s.obs, nbs[i], M[i])
        if rng.random() < a.eps:   # bruit d'exploration : etiquette = action du professeur, mais l'etat visite diverge
            legal = np.flatnonzero(M[i]); at[i] = rng.choice(legal); af[i] = rng.randrange(len(spec.FRACS))
        else: at[i], af[i] = t, f
        xs.append(X[i]); ms.append(M[i]); ts.append(t); fs.append(f)   # etiquette = professeur (DAgger-lite)
    _, done, info = venv.step(at, af, nbs); ends += [x for x in info if x]; X, M, nbs = venv.featurize()
    if step % 50 == 0: print(step, len(xs), f"{time.time()-t0:.0f}s", flush=True)
pathlib.Path(a.out).parent.mkdir(exist_ok=True)
np.savez_compressed(a.out, x=np.stack(xs), m=np.stack(ms), t=np.array(ts), f=np.array(fs))
print("demos:", len(xs), "episodes finis:", len(ends), "ends:", {e: sum(1 for x in ends if x["end"] == e) for e in {x["end"] for x in ends}}, "type hist:", np.bincount(ts, minlength=spec.N_TYPES).tolist())
venv.close()
