"""Evaluation reproductible v2 : memes parties (cartes/difficulte/bots/seeds) pour tous les agents ; IC de Wilson ; cartes d'entrainement vs JAMAIS VUES.
Agents : 'teacher' | 'random' | chemin de checkpoint (politique GREEDY). Toutes les parties specifiees sont jouees jusqu'au bout (pas de biais d'arret precoce)."""
import sys, json, math, time, pathlib, argparse, random, collections
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import numpy as np
from ofsi.rl2 import space as S
from ofsi.rl2.vecenv2 import VecEnv2
from ofsi.rl2.memguard import wait_ram
from ofsi.rl2.teacher_v2 import TeacherV2
from ofsi.rl2.teacher_v3 import TeacherV3

TRAIN_MAPS = ["Onion", "Pangaea", "Caucasus", "BosphorusStraits", "Iceland", "BeringStrait", "DanishStraits", "BlackSea"]
HELDOUT_MAPS = ["Africa", "Oceania", "MississippiRiver", "AmazonRiver"]


def wilson(k, n, z=1.96):
    if n == 0: return [None, None]
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)); return [round((c - r) / d, 3), round((c + r) / d, 3)]


def make_specs(maps, diffs, bots, per, seed0):
    specs, k = [], 0
    for m in maps:
        for d in diffs:
            for g in range(per):
                k += 1; specs.append({"map": m, "difficulty": d, "bots": bots[(g + k) % len(bots)], "_seed": f"e{seed0 + k:08d}", "_id": k})
    return specs


def evaluate(agent, specs, envs=12, max_steps=1500, device=None, agent_params="", sample=False, torch_seed=0):
    import torch
    device = device or ("cuda" if torch.cuda.is_available() else "cpu"); torch.manual_seed(torch_seed)
    from ofsi.rl2.model import PolicyV2, collate
    from ofsi.rl2 import ckpt
    queue = list(specs); lock = [0]; filler = {"map": "Onion", "difficulty": "Easy", "bots": 4, "_filler": True, "_seed": "f00000000", "_id": -1}

    def cfg():
        if queue: c = queue.pop(0); return c
        lock[0] += 1; return dict(filler, _seed=f"f{lock[0]:08d}")
    model = None
    if agent not in ("teacher", "teacher3", "random"):
        model = ckpt.build_model(ckpt.load(agent, device), device); model.eval()
    wait_ram(0.45 * envs + 2.0, tag=" eval2")
    bf16 = device == "cuda" and torch.cuda.is_bf16_supported(including_emulation=False)
    env = VecEnv2(envs, cfg, max_steps=max_steps); tparams = json.loads(agent_params) if agent_params else {}; TCls = TeacherV3 if agent == "teacher3" else TeacherV2; tea = [TCls(seed=i, **tparams) for i in range(envs)]; rng = random.Random(0)
    done_ids = {}; usage = collections.Counter(); todo = {s["_id"] for s in specs}; t0 = time.time()
    try:
        while todo - set(done_ids):
            acts = [None] * envs
            if model is not None:
                idx = [i for i in range(envs) if env.obs[i] is not None]
                if idx:
                    with torch.no_grad(), torch.autocast(device_type="cuda", dtype=torch.bfloat16, enabled=bf16): out = model.act(collate([env.obs[i] for i in idx], device), greedy=not sample)
                for r, i in enumerate(idx):
                    A = []
                    for k in range(S.M_SUB):
                        t = int(out["types"][r, k])
                        if t == S.T["STOP"]: break
                        A.append((t, int(out["ptrs"][r, k]), int(out["params"][r, k])))
                    acts[i] = A
            for i in range(envs):
                o = env.obs[i]
                if o is None: acts[i] = []; continue
                if agent in ("teacher", "teacher3"): st, costs, cands = env.sess[i].cur; acts[i] = tea[i].act(o, st, costs, cands)
                elif agent == "random":
                    A = []
                    if env.sess[i].last["state"].get("spawnPhase"):
                        pl = np.flatnonzero(o["ptr_mask"][S.T["SPAWN"]]); acts[i] = [(S.T["SPAWN"], int(rng.choice(list(pl))), 0)] if len(pl) else []; continue
                    for _ in range(rng.randint(0, 2)):
                        tl = np.flatnonzero(o["type_mask"]); tl = [t for t in tl if t != S.T["STOP"]]
                        if not tl: break
                        t = rng.choice(tl); pl = np.flatnonzero(o["ptr_mask"][t]); A.append((t, int(rng.choice(list(pl))) if len(pl) else 0, rng.randrange(len(S.FRACS))))
                    acts[i] = A
                for t, _, _ in acts[i]: usage[S.TYPES[t]] += 1
            rew, done, info = env.step(acts)
            for i, inf in enumerate(info):
                if inf and not inf["cfg"].get("_filler") and inf["cfg"]["_id"] not in done_ids:
                    done_ids[inf["cfg"]["_id"]] = {"cfg": {k: v for k, v in inf["cfg"].items()}, "end": inf["end"], "win": bool(inf["win"]), "progress": inf["progress"], "steps": inf["steps"], "tick": inf["tick"]}
                if inf and agent in ("teacher", "teacher3"): tea[i] = TCls(seed=len(done_ids) + 50, **tparams)
    finally:
        env.close()
    return list(done_ids.values()), usage, round(time.time() - t0)


def summarize(res):
    out = {}
    for name, sel in (("TOUT", lambda r: True), ("cartes_entrainement", lambda r: r["cfg"]["map"] in TRAIN_MAPS), ("cartes_jamais_vues", lambda r: r["cfg"]["map"] in HELDOUT_MAPS)):
        sub = [r for r in res if sel(r)]; out[name] = {}
        for d in ["Easy", "Medium", "Hard", "Impossible", "ALL"]:
            g = [r for r in sub if d == "ALL" or r["cfg"]["difficulty"] == d]
            if not g: continue
            k = sum(r["win"] for r in g); out[name][d] = {"parties": len(g), "victoires": k, "taux": round(k / len(g), 3), "ic95": wilson(k, len(g)), "progression_moy": round(float(np.mean([r["progress"] for r in g])), 3), "morts": sum(r["end"] == "dead" for r in g), "timeouts": sum(r["end"] == "timeout" for r in g)}
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--agent", required=True); ap.add_argument("--per", type=int, default=2, help="parties par (carte, difficulte)")
    ap.add_argument("--difficulties", default="Easy,Medium"); ap.add_argument("--maps", default="train+heldout"); ap.add_argument("--bots", default="8,12"); ap.add_argument("--envs", type=int, default=12)
    ap.add_argument("--seed0", type=int, default=1000000); ap.add_argument("--out", default=""); ap.add_argument("--max-steps", type=int, default=1500); ap.add_argument("--agent-params", default=""); ap.add_argument("--sample", action="store_true", help="politique ECHANTILLONNEE (graine torch fixe) au lieu de gloutonne"); ap.add_argument("--only", default="", help="ne jouer que cette difficulte, EN CONSERVANT les memes identifiants/seeds de parties")
    a = ap.parse_args(); maps = (TRAIN_MAPS if "train" in a.maps else []) + (HELDOUT_MAPS if "heldout" in a.maps else []); specs = make_specs(maps, a.difficulties.split(","), [int(x) for x in a.bots.split(",")], a.per, a.seed0)
    if a.only: specs = [x for x in specs if x["difficulty"] == a.only]
    res, usage, secs = evaluate(a.agent, specs, a.envs, a.max_steps, agent_params=a.agent_params, sample=a.sample); summ = summarize(res)
    rep = {"agent": a.agent, "specs": len(specs), "secondes": secs, "resume": summ, "usage_types": dict(usage.most_common()), "parties": res}
    out = a.out or f"benchmarks/eval2_{pathlib.Path(a.agent).parent.name if a.agent not in ('teacher', 'random') else a.agent}.json"; pathlib.Path(out).write_text(json.dumps(rep, indent=1), encoding="utf-8")
    for grp, g in summ.items():
        print(f"== {grp}")
        for d, v in g.items(): print(f"   {d:10s} {v['victoires']:3d}/{v['parties']:3d} = {v['taux']:.2f} IC95 {v['ic95']}  progression {v['progression_moy']}  morts {v['morts']} timeouts {v['timeouts']}")
    print("fichier:", out, "|", secs, "s")
