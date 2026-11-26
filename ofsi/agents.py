"""Agents de référence scriptés (professeurs / baselines). Ce ne sont PAS des modèles entraînés."""
import random

class ExpansionAgent:
    """Spawn sur un bon site, puis attaque la terre neutre en continu, garde une réserve."""
    name = "expansion_v0"
    def __init__(self, idx, cid, rng_seed=0, attack_every=10, send_frac=0.45, reserve=0.25):
        self.idx, self.cid, self.rng = idx, cid, random.Random(rng_seed)
        self.attack_every, self.send_frac, self.reserve = attack_every, send_frac, reserve
    def spawn(self, candidates):
        return [{"type": "spawn", "tile": self.rng.choice(candidates), "clientID": self.cid}]
    def act(self, tick, obs, env=None):
        s = obs.get("self", {})
        if not s.get("alive"): return []  # la cadence est fixée par l'appelant (decide_every)
        troops = int(s["troops"] * self.send_frac)
        if troops < 1000: return []
        return [{"type": "attack", "targetID": None, "troops": troops, "clientID": self.cid}]

class IdleAgent:
    name = "idle"
    def __init__(self, idx, cid, **kw): self.idx, self.cid = idx, cid
    def spawn(self, candidates): return [{"type": "spawn", "tile": candidates[len(candidates)//2], "clientID": self.cid}]
    def act(self, tick, obs, env=None): return []

class RandomLegalAgent:
    """Agit au hasard parmi des actions toujours légales côté moteur (attaque neutre avec fraction aléatoire, ou rien)."""
    name = "random_legal_v0"
    def __init__(self, idx, cid, rng_seed=0, **kw): self.idx, self.cid, self.rng = idx, cid, random.Random(rng_seed)
    def spawn(self, candidates): return [{"type": "spawn", "tile": self.rng.choice(candidates), "clientID": self.cid}]
    def act(self, tick, obs, env=None):
        s = obs.get("self", {})
        if not s.get("alive") or self.rng.random() < 0.5: return []
        return [{"type": "attack", "targetID": None, "troops": int(s["troops"] * self.rng.choice([0.05, 0.1, 0.2, 0.4])), "clientID": self.cid}]


class ConquerorAgent:
    """Professeur scripte : economie (villes) + conquete opportuniste du voisin le plus faible + expansion mesuree. NON entraine."""
    name = "conqueror_v1"
    def __init__(self, idx, cid, rng_seed=0, ratio=1.6, send=0.6, expand=0.25, **kw):
        self.idx, self.cid, self.rng = idx, cid, random.Random(rng_seed); self.ratio, self.send, self.expand = ratio, send, expand
    def spawn(self, candidates): return [{"type": "spawn", "tile": self.rng.choice(candidates), "clientID": self.cid}]
    def act(self, tick, obs, env=None):
        s = obs.get("self", {})
        if not s.get("alive"): return []
        out = []; troops = s["troops"]; costs = obs.get("costs") or {}
        if env is not None and s["gold"] >= costs.get("City", 1e18) and s["units"].get("City", 0) < 2 + s["tiles"] // 500:
            t = env.build_tiles("City", agent=self.idx)
            if t: out.append({"type": "build_unit", "unit": "City", "tile": t[0], "clientID": self.cid})
        nb = [o for o in obs["others"] if o["border"] and not o["allied"]]
        tgt = min(nb, key=lambda o: o["troops"]) if nb else None
        if tgt and troops > self.ratio * tgt["troops"]:
            out.append({"type": "attack", "targetID": tgt["id"], "troops": int(troops * self.send), "clientID": self.cid})
        elif troops > 3000:
            out.append({"type": "attack", "targetID": None, "troops": int(troops * self.expand), "clientID": self.cid})
        return out


_POLICY_CACHE = {}
class PolicyAgent:
    """Politique neuronale entrainee (checkpoint verifie par SHA256). greedy=True : argmax sur actions legales (evaluation reproductible)."""
    name = "policy"
    def __init__(self, idx, cid, rng_seed=0, ckpt=None, greedy=True, **kw):
        import torch
        from ofsi.rl.ppo import Policy, load_ckpt
        key = ckpt
        if key not in _POLICY_CACHE:
            torch.set_num_threads(1); m = Policy(); m.load_state_dict(load_ckpt(ckpt)["model"]); m.eval(); _POLICY_CACHE[key] = m
        self.model = _POLICY_CACHE[key]; self.idx, self.cid, self.rng = idx, cid, random.Random(rng_seed); self.greedy = greedy; self.n_start = None; self.torch = torch
    def spawn(self, candidates): return [{"type": "spawn", "tile": self.rng.choice(candidates), "clientID": self.cid}]
    def act(self, tick, obs, env=None):
        from ofsi.rl import spec
        if "self" not in obs or not obs["self"]["alive"]: return []
        if self.n_start is None: self.n_start = 1 + len(obs["others"])
        x, m, nb = spec.featurize(obs, self.n_start); T = self.torch
        with T.no_grad():
            dt, df, _ = self.model(T.from_numpy(x)[None], T.from_numpy(m)[None])
            at = int(dt.probs.argmax(-1)) if self.greedy else int(dt.sample()); af = int(df.probs.argmax(-1)) if self.greedy else int(df.sample())
        it, _ = spec.decode_intent(obs, self.cid, env, at, af, nb, agent=self.idx)
        return [it] if it else []
