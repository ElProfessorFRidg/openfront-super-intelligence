"""Collecte de trajectoires du professeur v2 (observations v2 completes + actions + recompenses + issue d'episode), en fragments compresses.
Stockage compact : float16 + masques empaquetes (quota disque : ~10 Ko/decision compresse). Les trajectoires PERDANTES sont conservees (WorldModel, analyse d'erreurs)."""
import sys, time, json, pathlib, argparse, random
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import numpy as np
from ofsi.rl2.vecenv2 import VecEnv2
from ofsi.rl2.teacher_v2 import TeacherV2
from ofsi.rl2 import space as S

F16 = ("self", "players", "units", "atts", "bank", "grid")
BOOL = ("pmask", "umask", "amask", "bmask", "type_mask")


def pack(o):
    d = {k: o[k].astype(np.float16) for k in F16}
    d.update({k: np.packbits(o[k].astype(np.uint8)) for k in BOOL}); d["ptr_mask"] = np.packbits(o["ptr_mask"].astype(np.uint8)); return d


def unpack(shard, idx):
    o = {k: shard[k][idx].astype(np.float32) for k in F16}
    for k, n in (("pmask", S.N_PLAYERS), ("umask", S.N_UNITS), ("amask", S.N_ATT), ("bmask", S.NB), ("type_mask", S.NT)): o[k] = np.unpackbits(shard[k][idx])[:n].astype(bool)
    o["ptr_mask"] = np.unpackbits(shard["ptr_mask"][idx])[:S.NT * S.NB].reshape(S.NT, S.NB).astype(bool); return o


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--maps", default="Onion"); ap.add_argument("--difficulties", default="Easy"); ap.add_argument("--bots", default="8"); ap.add_argument("--envs", type=int, default=12)
    ap.add_argument("--decisions", type=int, default=20000); ap.add_argument("--out", default="data/demos_v2"); ap.add_argument("--max-steps", type=int, default=1500)
    ap.add_argument("--shard", type=int, default=2000); ap.add_argument("--teacher-params", default="{}"); ap.add_argument("--seed", type=int, default=0); ap.add_argument("--eps", type=float, default=0.0, help="bruit d'exploration (action aleatoire legale) ; etiquette = professeur")
    a = ap.parse_args(); out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    maps, diffs, bots = a.maps.split(","), a.difficulties.split(","), [int(x) for x in a.bots.split(",")]; rng = random.Random(a.seed); lock = [0]

    def cfg(): lock[0] += 1; return {"map": rng.choice(maps), "bots": rng.choice(bots), "difficulty": rng.choice(diffs)}
    env = VecEnv2(a.envs, cfg, max_steps=a.max_steps); tp = json.loads(a.teacher_params); teachers = [TeacherV2(seed=a.seed * 1000 + i, **tp) for i in range(a.envs)]
    buf = {}; eps = [[] for _ in range(a.envs)]; ep_counter = 0; n = 0; shard_i = 0; t0 = time.time(); stats = {"episodes": 0, "wins": 0, "decisions": 0}; meta = []

    def flush(final=False):
        nonlocal buf, shard_i
        if not buf or (len(buf["reward"]) < a.shard and not final): return
        np.savez_compressed(out / f"shard_{a.seed}_{shard_i:04d}.npz", **{k: np.stack(v) for k, v in buf.items()}); shard_i += 1; buf = {}
    while n < a.decisions:
        acts, rec = [], []
        for i in range(a.envs):
            o = env.obs[i]
            if o is None: acts.append([]); rec.append(None); continue
            st, costs, cands = env.sess[i].cur; A = teachers[i].act(o, st, costs, cands)
            lab = (A + [(0, 0, 0)] * S.M_SUB)[:S.M_SUB]
            if a.eps > 0 and rng.random() < a.eps:                  # divergence d'etat : on EXECUTE une action legale aleatoire, l'etiquette reste celle du professeur
                tl = np.flatnonzero(o["type_mask"]); t = int(rng.choice(list(tl))); pl = np.flatnonzero(o["ptr_mask"][t]); A = [(t, int(rng.choice(list(pl))) if len(pl) else 0, rng.randrange(len(S.FRACS)))]
            acts.append(A); rec.append((pack(o), np.array([x[0] for x in lab]), np.array([x[1] for x in lab]), np.array([x[2] for x in lab])))
        rew, done, info = env.step(acts)
        for i in range(a.envs):
            if rec[i] is None: continue
            p, t, q, r_ = rec[i]; eps[i].append((p, t, q, r_, rew[i]))
            if done[i]:
                inf = info[i]; ep_counter += 1; E = eps[i]; ret = 0.0; rets = []
                for x in reversed(E): ret = x[4] + 0.997 * ret; rets.append(ret)
                rets.reverse()
                for j, x in enumerate(E):
                    for k, v in x[0].items(): buf.setdefault(k, []).append(v)
                    buf.setdefault("types", []).append(x[1]); buf.setdefault("ptrs", []).append(x[2]); buf.setdefault("params", []).append(x[3])
                    buf.setdefault("reward", []).append(np.float32(x[4])); buf.setdefault("ret", []).append(np.float32(rets[j])); buf.setdefault("ep", []).append(np.int32(ep_counter + a.seed * 100000))
                    buf.setdefault("step", []).append(np.int32(j)); buf.setdefault("win", []).append(np.int8(inf["win"])); buf.setdefault("last", []).append(np.int8(j == len(E) - 1))
                n += len(E); stats["episodes"] += 1; stats["wins"] += int(inf["win"]); stats["decisions"] = n
                meta.append({"ep": ep_counter + a.seed * 100000, "map": inf["cfg"]["map"], "difficulty": inf["cfg"]["difficulty"], "bots": inf["cfg"]["bots"], "end": inf["end"], "win": inf["win"], "steps": inf["steps"], "tick": inf["tick"], "progress": inf["progress"]})
                eps[i] = []; teachers[i] = TeacherV2(seed=a.seed * 1000 + ep_counter + 7, **tp); flush()
                print(f"[{n:6d}/{a.decisions}] ep {ep_counter:4d} {inf['cfg']['map']:12s} {inf['cfg']['difficulty']:10s} {inf['end']:18s} steps={inf['steps']:4d} prog={inf['progress']:.2f} | victoires {stats['wins']}/{stats['episodes']} | {n/(time.time()-t0):.0f} dec/s", flush=True)
    flush(final=True); (out / f"meta_{a.seed}.json").write_text(json.dumps({"stats": stats, "episodes": meta, "args": vars(a), "seconds": round(time.time() - t0)}, indent=1), encoding="utf-8"); env.close(); print("termine", stats)


if __name__ == "__main__":
    main()
