"""Session d'environnement v2 : un agent, observations riches + candidats legaux (cache a duree de vie courte pour les requetes coûteuses)."""
import random
import numpy as np
from ofsi.client import OFEnvProc
from ofsi.rl2 import space as S

TTL = {"boat": 8, "tiles": 4, "upgrade": 4, "nuke": 3, "warship": 6}      # en decisions
_LAND_CACHE = {}


class Session:
    def __init__(self, decide_every=20, max_steps=1500):
        self.e = OFEnvProc(); self.de = decide_every; self.max_steps = max_steps
        self.cid = None; self.cfg = None; self.step_i = 0; self.cache = {}; self.grid = np.zeros((4, S.G, S.G), np.float32); self.grid_at = -99
        self.land_total = 1; self.n_start = 1; self.spawn_cands = []; self.last = None; self.pot = 0.0; self.invalid_exec = 0; self.exec_n = 0

    # ---------- cycle de vie ----------
    def start(self, cfg, seed):
        self.cfg = cfg; self.step_i = 0; self.cache = {}; self.grid_at = -99
        r = self.e.reset(map=cfg["map"], seed=seed, agents=1, bots=cfg["bots"], difficulty=cfg["difficulty"], nations=cfg.get("nations", "default")); self.cid = r["agentIds"][0]
        key = cfg["map"]
        if key not in _LAND_CACHE:
            sizes, _ = self.e.landmasses([]); _LAND_CACHE[key] = sum(sizes)
        self.land_total = _LAND_CACHE[key]
        c = self.e.spawn_candidates(stride=10, min_tiles=40); sizes, of = self.e.landmasses(c)
        W = r["mapW"]; rng = random.Random(seed)
        idx = list(range(len(c))); rng.shuffle(idx); idx = sorted(idx[:64])
        self.spawn_cands = [(c[i] % W, c[i] // W, sizes[of[i]] / self.land_total, c[i]) for i in idx]
        self.W, self.H = W, r["mapH"]
        s = self.e.step_state(1)                            # etat initial (phase de spawn)
        self.last = s; self.n_start = 1; self.pot = 0.0
        return self.observe()

    def close(self): self.e.close()

    # ---------- candidats ----------
    def _fresh(self, key, ttl):
        c = self.cache.get(key)
        return c is not None and self.step_i - c[0] < ttl

    def _cands(self, st, costs):
        s = st["self"]; out = {}
        if st.get("spawnPhase"): return {"spawn": self.spawn_cands}
        gold, u = s["gold"], s["units"]
        def get(key, ttl, fn):
            if not self._fresh(key, ttl): self.cache[key] = (self.step_i, fn())
            return self.cache[key][1]
        if s["boats"] < s["boatsMax"] and s["troops"] > 5000: out["boat"] = get("boat", TTL["boat"], lambda: self.e.cands("boat", max=24))
        aff = [k for k in S.BUILD_KINDS if gold >= costs.get(k, 1e18)]
        if aff:                                                    # UN seul passage moteur pour tous les types abordables
            allc = get("tiles_all|" + ",".join(aff), TTL["tiles"], lambda: self.e.cands("build_all", units=aff, max=16, probe=160))
            for k in aff: out["tiles_" + k] = allc.get(k, [])
        if gold > 1000: out["upgrade"] = get("upgrade", TTL["upgrade"], lambda: self.e.cands("upgrade"))
        if u.get("Missile Silo", 0) > 0 and gold >= costs.get("Atom Bomb", 1e18): out["nuke"] = get("nuke", TTL["nuke"], lambda: self.e.cands("nuke", unit="Atom Bomb", max=16))
        if (u.get("Port", 0) > 0 and gold >= costs.get("Warship", 1e18)) or u.get("Warship", 0) > 0: out["warship"] = get("warship", TTL["warship"], lambda: self.e.cands("warship", max=8))
        return out

    def _grid(self):
        if self.step_i - self.grid_at >= 5:
            g = self.e.grid2(); a = np.zeros((4, S.G, S.G), np.float32)
            d = np.array(g["data"], np.float32).reshape(g["gh"], g["gw"], 4).transpose(2, 0, 1); a[:, :g["gh"], :g["gw"]] = d; self.grid = a; self.grid_at = self.step_i
        return self.grid

    # ---------- observation / action ----------
    def _blank_state(self, st):
        """Etat neutre pour la phase de spawn (l'agent n'existe pas encore dans le moteur)."""
        z = {"id": "", "alive": True, "spawned": False, "immune": False, "traitor": False, "decaying": False, "gold": 0, "troops": 0, "maxTroops": 1, "tiles": 0, "borderTiles": 0, "tradeGold": 0,
             "trainGold": 0, "piracyGold": 0, "goldEarned": 0, "allies": [], "tradingPartners": 0, "canEmbargoAll": False, "boatsMax": 1, "boats": 0, "units": {}, "incomingAllianceRequests": []}
        return {"tick": st.get("tick", 0), "spawnPhase": True, "map": {"w": self.W, "h": self.H}, "win": {"landTiles": self.land_total, "thresholdTenths": 800}, "self": z, "units": [],
                "outgoingAttacks": [], "incomingAttacks": [], "players": [], "nOthersAlive": 0}

    def observe(self):
        st, costs = self.last["state"], self.last["costs"]
        if "self" not in st:
            if not st.get("spawnPhase"): return None                      # agent elimine / absent hors spawn
            st = self._blank_state(st)
        cands = self._cands(st, costs)
        if self.step_i == 0 and not st.get("spawnPhase"): self.n_start = 1 + st["nOthersAlive"]
        ctx = {"land_total": self.land_total, "n_start": self.n_start, "grid": self._grid() if not st.get("spawnPhase") else self.grid}
        obs = S.build_obs(st, costs, cands, ctx); self.cur = (st, costs, cands)
        return obs

    def apply(self, actions):
        """actions : liste de (type, indice_banque, parametre). Retourne le resultat du step."""
        st, costs, cands = self.cur; intents = []
        for t, ptr, par in actions[:S.M_SUB]:
            try: it = S.decode(t, ptr, par, st, cands, st["units"])
            except Exception: it = None; self.invalid_exec += 1
            self.exec_n += 1
            if it is not None: it["clientID"] = self.cid; intents.append(it)
        ticks = 1 if st.get("spawnPhase") else self.de
        self.last = self.e.step_state(ticks, intents); self.step_i += 1
        return self.last

    def spawn_wait(self):
        """Apres le spawn, laisser la phase de spawn se terminer."""
        while True:                                   # pas de 40 ticks sans etat (bon marche), puis UN seul releve d'etat
            r = self.e.step(40)
            if not r.get("spawnPhase", False): break
        self.last = self.e.step_state(0)
        self.step_i = 0
        return self.observe()
