"""Environnement vectorisé : N processus Node indépendants, pas synchrone (envoi à tous puis lecture), reset automatique."""
import random, numpy as np
from ofsi.client import OFEnvProc
from ofsi.rl import spec

WIN_R, DEATH_R, SHAPE = 2.0, -1.0, 2.0   # récompense terminale cohérente avec la victoire ; façonnage = potentiel (part de terre) -> invariance de politique

class Slot:
    def __init__(self, i): self.i = i; self.env = OFEnvProc(); self.cid = None; self.cfg = None; self.obs = None; self.pot = 0.0; self.steps = 0; self.n_start = 1; self.ep_ret = 0.0; self.ep_id = 0
    def start(self, cfg, seed):
        self.cfg = cfg; self.ep_id += 1
        r = self.env.reset(map=cfg["map"], seed=seed, agents=1, bots=cfg["bots"], difficulty=cfg["difficulty"]); self.cid = r["agentIds"][0]
        c = self.env.spawn_candidates(); tile = random.Random(seed).choice(c)    # spawn SCRIPTÉ en v1 (SpawnNet à venir)
        s = self.env.step_obs(1, [{"type": "spawn", "tile": tile, "clientID": self.cid}], costs=True)
        while s["spawnPhase"]: s = self.env.step_obs(1, costs=True)
        self.obs = s["obs"][0]; self.n_start = 1 + len(self.obs["others"]); self.pot = spec.share(self.obs); self.steps = 0; self.ep_ret = 0.0

class VecEnv:
    def __init__(self, n, cfg_fn, decide_every=20, max_steps=1500):
        self.n, self.cfg_fn, self.de, self.max_steps = n, cfg_fn, decide_every, max_steps
        self.slots = [Slot(i) for i in range(n)]; self.counter = 0; self.invalid_exec = 0; self.exec_actions = 0
        for s in self.slots: self._start(s)
    def _start(self, s):
        self.counter += 1; s.start(self.cfg_fn(), f"v{self.counter:08d}")
    def featurize(self):
        out = [spec.featurize(s.obs, s.n_start) for s in self.slots]
        return np.stack([o[0] for o in out]), np.stack([o[1] for o in out]), [o[2] for o in out]
    def _intent(self, s, a_type, frac_i, nb):
        it, failed = spec.decode_intent(s.obs, s.cid, s.env, a_type, frac_i, nb)
        if spec.T_BUILD <= a_type < spec.T_ALLY: self.exec_actions += 1; self.invalid_exec += int(failed)
        return it
    def step(self, a_types, frac_is, nbs):
        for s, t, f, nb in zip(self.slots, a_types, frac_is, nbs):
            intent = self._intent(s, int(t), int(f), nb); s.env.send("step_obs", ticks=self.de, intents=[intent] if intent else [], agents=[0], costs=True)
        rew = np.zeros(self.n, np.float32); done = np.zeros(self.n, bool); info = [None] * self.n
        for i, s in enumerate(self.slots):
            r = s.env.recv(); s.steps += 1; o = r["obs"][0]; ended = None
            if not r["ok"]: ended = "engine_error"
            alive = o.get("self", {}).get("alive", False) if "self" in o else False
            win = r.get("winner") is not None and "self" in o and r["winner"] == o["self"]["id"]
            if win: ended = "win"
            elif r.get("winner") is not None: ended = "loss_winner_other"
            elif not alive: ended = "dead"
            elif s.steps >= self.max_steps: ended = "timeout"
            pot = spec.share(o) if "self" in o else 0.0
            rew[i] = SHAPE * (pot - s.pot) + (WIN_R if win else DEATH_R if ended in ("dead", "loss_winner_other") else 0.0)
            s.pot = pot; s.ep_ret += rew[i]
            if ended:
                done[i] = True; info[i] = {"end": ended, "win": win, "ret": float(s.ep_ret), "steps": s.steps, "cfg": s.cfg, "tick": r["tick"], "peak_share": pot}
                if ended == "engine_error": s.env.close(); s.env = OFEnvProc(); s.cid = None
                self._start(s)
            else: s.obs = o
        return rew, done, info
    def close(self):
        for s in self.slots: s.env.close()
