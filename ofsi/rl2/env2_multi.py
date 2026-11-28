"""Partie MULTI-AGENTS : k agents pilotes de l'exterieur (politiques neuronales gelees, professeurs, aleatoire...) dans le MEME moteur, plus bots/nations.
Reutilise Session (observations, candidats, decodage) via un proxy qui oriente chaque requete vers l'agent voulu : aucune duplication de la logique d'observation."""
import random
import numpy as np
from ofsi.client import OFEnvProc
from ofsi.rl2 import space as S
from ofsi.rl2.env2 import Session, _LAND_CACHE


class _Proxy:
    """Fait croire a une Session qu'elle parle a un moteur dedie a l'agent `idx`."""
    def __init__(self, env, idx): self.env, self.idx = env, idx
    def cands(self, kind, **kw): return self.env.cands(kind, agent=self.idx, **kw)
    def grid2(self, **kw): return self.env.grid2(agent=self.idx, **kw)
    def step_state(self, ticks=1, intents=None, **kw): raise RuntimeError("le pas de jeu est pilote par MultiSession")
    def close(self): pass


class MultiSession:
    def __init__(self, k, decide_every=20, max_steps=1500):
        self.k, self.de, self.max_steps = k, decide_every, max_steps
        self.e = OFEnvProc(); self.views = [Session.__new__(Session) for _ in range(k)]
        for i, v in enumerate(self.views):
            v.e = _Proxy(self.e, i); v.de, v.max_steps = decide_every, max_steps; v.cid = None; v.cfg = None; v.step_i = 0; v.cache = {}; v.grid = np.zeros((4, S.G, S.G), np.float32); v.grid_at = -99
            v.land_total = 1; v.n_start = 1; v.spawn_cands = []; v.last = None; v.pot = 0.0; v.invalid_exec = 0; v.exec_n = 0; v.W = v.H = 0
        self.steps = 0; self.tick = 0; self.winner = None; self.spawn_missing = []

    def start(self, cfg, seed):
        e = self.e; r = e.reset(map=cfg["map"], seed=seed, agents=self.k, bots=cfg["bots"], difficulty=cfg["difficulty"], nations=cfg.get("nations", "default")); self.cids = r["agentIds"]
        key = cfg["map"]
        if key not in _LAND_CACHE: sizes, _ = e.landmasses([]); _LAND_CACHE[key] = sum(sizes)
        land = _LAND_CACHE[key]; W = r["mapW"]; c = e.spawn_candidates(stride=10, min_tiles=40); sizes, of = e.landmasses(c)
        rng = random.Random(seed); idx = list(range(len(c))); rng.shuffle(idx); idx = sorted(idx[:64]); sp = [(c[i] % W, c[i] // W, sizes[of[i]] / land, c[i]) for i in idx]
        s0 = e.step_state(1, agent=0)
        for i, v in enumerate(self.views):
            v.cid, v.cfg, v.land_total, v.spawn_cands, v.W, v.H = self.cids[i], cfg, land, sp, W, r["mapH"]; v.step_i = 0; v.cache = {}; v.grid_at = -99
            v.last = s0 if i == 0 else {**s0, **{k2: e.state2(i)[k2] for k2 in ("state", "costs")}}
        self.steps = 0; self.winner = None; self.spawn_missing = []; self.tick = s0["tick"]
        return [v.observe() for v in self.views]

    def step(self, actions):
        """actions : liste (une par agent) de [(type, ptr, param), ...]. Retourne (obs_list, info)."""
        intents = []; spawn_phase = bool(self.views[0].last["state"].get("spawnPhase"))
        for i, v in enumerate(self.views):
            st, costs, cands = v.cur
            for t, p, par in (actions[i] or [])[:S.M_SUB]:
                try: it = S.decode(t, p, par, st, cands, st["units"])
                except Exception: it = None; v.invalid_exec += 1
                v.exec_n += 1
                if it is not None: it["clientID"] = self.cids[i]; intents.append(it)
        e = self.e; r0 = e.step_state(1 if spawn_phase else self.de, intents, agent=0); self.steps += 1; self.tick = r0["tick"]
        if spawn_phase:
            while True:
                r = e.step(40)
                if not r.get("spawnPhase", False): break
            r0 = e.step_state(0, agent=0); self.tick = r0["tick"]
        for i, v in enumerate(self.views):
            v.last = r0 if i == 0 else {**r0, **{k2: e.state2(i)[k2] for k2 in ("state", "costs")}}; v.step_i += 1
        if spawn_phase: self.spawn_missing = [i for i, v in enumerate(self.views) if "self" not in v.last["state"] or v.last["state"]["self"].get("tiles", 0) == 0]     # VRAI echec d'apparition : agent absent/sans tuile a la FIN de la phase de spawn
        w = r0.get("winner"); self.winner = w
        status = []
        for i, v in enumerate(self.views):
            st = v.last["state"]; alive = "self" in st and st["self"]["alive"]; mine = st["self"]["id"] if "self" in st else None
            win = w is not None and mine is not None and w == mine
            end = "win" if win else ("loss_winner_other" if w is not None else ("dead" if not alive and not st.get("spawnPhase") else None))
            tiles = st["self"]["tiles"] if "self" in st else 0; wl = (st.get("win") or {}).get("landTiles", 1) or 1
            status.append({"agent": i, "end": end, "win": win, "alive": alive, "tiles": tiles, "progress": tiles / (wl * 0.8)})
        done = w is not None or all(s["end"] is not None for s in status) or self.steps >= self.max_steps
        obs = [v.observe() if (status[i]["alive"] or spawn_phase) else None for i, v in enumerate(self.views)]
        return obs, {"status": status, "done": done, "tick": self.tick, "winner": w, "timeout": self.steps >= self.max_steps and w is None}

    def close(self): self.e.close()
