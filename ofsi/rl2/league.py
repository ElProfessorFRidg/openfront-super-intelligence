"""Ligue locale : agents heterogenes dans le meme moteur (MultiSession), matrice de confrontations, classement Bradley-Terry avec IC par bootstrap,
et regle de promotion d'un champion fondee sur une borne statistique + absence de regression. Tout est mesure ; rien n'est suppose.
Agents : 'random' | 'teacher2' | 'teacher3' | <chemin de checkpoint .pt> (politique greedy)."""
import sys, json, math, time, random, pathlib, argparse, itertools, collections
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import numpy as np
from ofsi.rl2 import space as S
from ofsi.rl2.env2_multi import MultiSession
from ofsi.rl2.teacher_v2 import TeacherV2
from ofsi.rl2.teacher_v3 import TeacherV3


class RandomAgent:
    def __init__(self, seed=0): self.rng = random.Random(seed)
    def act(self, obs, st, costs, cands):
        if st.get("spawnPhase"):                      # une seule decision de spawn : l'agent aleatoire doit SPAWN (sinon partie invalide)
            pl = np.flatnonzero(obs["ptr_mask"][S.T["SPAWN"]]); return [(S.T["SPAWN"], int(self.rng.choice(list(pl))), 0)] if len(pl) else []
        A = []
        for _ in range(self.rng.randint(0, 2)):
            tl = [t for t in np.flatnonzero(obs["type_mask"]) if t != S.T["STOP"]]
            if not tl: break
            t = self.rng.choice(tl); pl = np.flatnonzero(obs["ptr_mask"][t]); A.append((int(t), int(self.rng.choice(list(pl))) if len(pl) else 0, self.rng.randrange(len(S.FRACS))))
        return A


class TeacherAgent:
    def __init__(self, cls, seed=0, **kw): self.t = cls(seed=seed, **kw)
    def act(self, obs, st, costs, cands): return self.t.act(obs, st, costs, cands)


class NeuralAgent:
    _cache = {}
    def __init__(self, ckpt, device=None, sample=True, seed=0):
        import torch
        torch.manual_seed(seed); self.sample = sample          # ECHANTILLONNE par defaut : le decodage glouton fausse les politiques PPO (cf. journal 2026-11-26)
        device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        from ofsi.rl2.model import PolicyV2, collate
        from ofsi.rl2 import ckpt as C
        self.torch, self.collate, self.dev = torch, collate, device
        self.bf16 = device == "cuda" and torch.cuda.is_bf16_supported(including_emulation=False)
        key = (ckpt, device)
        if key not in NeuralAgent._cache:
            m = PolicyV2().to(device); m.load_state_dict(C.load(ckpt, device)["model"]); m.eval(); NeuralAgent._cache[key] = m
        self.m = NeuralAgent._cache[key]
    def act(self, obs, st, costs, cands):
        T = self.torch
        with T.no_grad(), T.autocast(device_type="cuda", dtype=T.bfloat16, enabled=self.bf16): out = self.m.act(self.collate([obs], self.dev), greedy=not self.sample)
        A = []
        for k in range(S.M_SUB):
            t = int(out["types"][0, k])
            if t == S.T["STOP"]: break
            A.append((t, int(out["ptrs"][0, k]), int(out["params"][0, k])))
        return A


def make_agent(spec, seed=0, *, device=None):
    if spec == "random": return RandomAgent(seed)
    if spec == "teacher2": return TeacherAgent(TeacherV2, seed, ally_mode="none")
    if spec == "teacher_threats": return TeacherAgent(TeacherV2, seed, ally_mode="threats")
    if spec == "teacher3": return TeacherAgent(TeacherV3, seed)
    return NeuralAgent(spec, device=device)


def play(specs, cfg, seed, max_steps=1500):
    """Joue UNE partie avec len(specs) agents ; retourne par agent : victoire, tuiles finales, progression, vivant."""
    ms = MultiSession(len(specs), max_steps=max_steps); ag = [make_agent(s, seed=i + hash(seed) % 1000) for i, s in enumerate(specs)]
    try:
        obs = ms.start(cfg, seed); info = None
        while True:
            acts = [ag[i].act(obs[i], *ms.views[i].cur) if obs[i] is not None else [] for i in range(len(specs))]
            obs, info = ms.step(acts)
            if info["done"]: break
        st = info["status"]; fail = any(s["tiles"] == 0 and s["end"] != "win" and ms.views[i].last["state"].get("self", {}).get("spawned", True) is False for i, s in enumerate(st))
        return {"specs": specs, "cfg": cfg, "seed": seed, "tick": info["tick"], "timeout": info["timeout"], "status": st, "spawn_failed": bool(ms.spawn_missing), "spawn_missing": list(ms.spawn_missing)}   # PAS « un agent est mort » (defaut corrige le 2026-11-27 : excluait les parties decisives)
    finally:
        ms.close()


def pair_outcome(a, b):
    """1 si a bat b, 0 si b bat a, 0.5 sinon : victoire de partie d'abord, puis tuiles finales."""
    if a["win"] != b["win"]: return 1.0 if a["win"] else 0.0
    if a["tiles"] == b["tiles"]: return 0.5
    return 1.0 if a["tiles"] > b["tiles"] else 0.0


def bradley_terry(names, games, iters=500):
    """games : liste de (i, j, score_i in [0,1]). MM de Hunter ; retourne des forces log-normalisees (Elo-like, 400/ln10 x theta)."""
    n = len(names); w = np.ones(n); W = np.zeros((n, n))
    for i, j, s in games: W[i, j] += s; W[j, i] += 1 - s
    for i in range(n):                                   # a priori faible : 1 partie virtuelle nulle (0,5/0,5) par paire -> forces finies meme avec 100 % de victoires
        for j in range(n):
            if i != j: W[i, j] += 0.25
    N = W + W.T
    for _ in range(iters):
        for i in range(n):
            den = sum(N[i, j] / (w[i] + w[j]) for j in range(n) if j != i and N[i, j] > 0)
            if den > 0: w[i] = max(1e-9, W[i].sum() / den)
        w = w / np.exp(np.mean(np.log(w)))
    return 400 / math.log(10) * np.log(w)


def rate(names, games, boots=300, seed=0):
    base = bradley_terry(names, games); rng = np.random.default_rng(seed); bs = []
    for _ in range(boots):
        idx = rng.integers(0, len(games), len(games)); bs.append(bradley_terry(names, [games[k] for k in idx], iters=120))
    bs = np.array(bs); return base, np.percentile(bs, 2.5, axis=0), np.percentile(bs, 97.5, axis=0)


def wilson_lower(k, n, z=1.96):
    if n == 0: return 0.0
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)); return (c - r) / d


def promote(h2h_wins, h2h_n, regress_worse, regress_better, min_n=40, alpha_floor=0.5):
    """Regle de promotion : (1) assez de duels directs ; (2) borne basse de Wilson du taux de victoire du candidat > 0.5 ; (3) pas de regression apparentee significative sur la batterie
    (McNemar exact unilateral : parties perdues seulement par le candidat vs gagnees seulement par lui, p > 0.10)."""
    ok_n = h2h_n >= min_n; lb = wilson_lower(h2h_wins, h2h_n); n = regress_worse + regress_better
    p_reg = sum(math.comb(n, k) for k in range(regress_worse, n + 1)) / 2 ** n if n else 1.0       # P(>= regress_worse | H0 neutre) : petit => le candidat perd significativement plus qu'il ne gagne = regression
    ok_reg = p_reg > 0.10
    return {"promote": bool(ok_n and lb > alpha_floor and ok_reg), "duels": h2h_n, "wilson_lower": round(lb, 3), "p_regression": round(p_reg, 3), "raisons": {"assez_de_duels": ok_n, "borne_basse>0.5": lb > alpha_floor, "pas_de_regression": ok_reg}}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--agents", required=True, help="liste separee par des virgules"); ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--maps", default="Onion,Pangaea,Caucasus"); ap.add_argument("--difficulty", default="Easy"); ap.add_argument("--bots", type=int, default=6); ap.add_argument("--out", default="benchmarks/league.json")
    a = ap.parse_args(); names = a.agents.split(","); maps = a.maps.split(","); games, matches = [], []; t0 = time.time(); seed = 0
    for (i, j) in itertools.combinations(range(len(names)), 2):
        for r in range(a.rounds):
            for mp in maps:
                for swap in (False, True):                                    # echange des sieges
                    seed += 1; order = [j, i] if swap else [i, j]; res = play([names[k] for k in order], {"map": mp, "bots": a.bots, "difficulty": a.difficulty}, f"lg{seed:08d}")
                    matches.append(res)
                    if res["spawn_failed"]: continue
                    sa, sb = res["status"][0], res["status"][1]; sc = pair_outcome(sa, sb); games.append((order[0], order[1], sc))
                    print(f"{names[order[0]][:28]:28s} vs {names[order[1]][:28]:28s} {mp:10s} -> {sc:.1f} (tuiles {sa['tiles']} / {sb['tiles']})", flush=True)
    if games:
        base, lo, hi = rate(names, games); table = [{"agent": n, "force_BT": round(float(b), 1), "ic95": [round(float(l), 1), round(float(h), 1)]} for n, b, l, h in zip(names, base, lo, hi)]
        W = np.zeros((len(names), len(names))); N = np.zeros_like(W)
        for i, j, s in games: W[i, j] += s; N[i, j] += 1; W[j, i] += 1 - s; N[j, i] += 1
        mat = [[(round(float(W[i, j] / N[i, j]), 2) if N[i, j] else None) for j in range(len(names))] for i in range(len(names))]
        print(json.dumps({"classement": sorted(table, key=lambda x: -x["force_BT"]), "matrice_taux_victoire_ligne_vs_colonne": mat}, ensure_ascii=False, indent=1))
        pathlib.Path(a.out).write_text(json.dumps({"agents": names, "matches": matches, "table": table, "matrice": mat, "secondes": round(time.time() - t0)}, indent=1), encoding="utf-8")
