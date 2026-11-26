"""Environnement vectorise v2 : N sessions (un processus moteur chacune), pas concurrent par threads, reset automatique.
Recompense : terminale cle sur la victoire (+3 / -1 / 0) + faconnage potentiel sur la progression vers le seuil de victoire REEL du moteur (invariance de politique)."""
import random
from concurrent.futures import ThreadPoolExecutor
from ofsi.rl2.env2 import Session
from ofsi.rl2 import space as S

WIN_R, LOSS_R, SHAPE = 3.0, -1.0, 3.0


def potential(st):
    if "self" not in st: return 0.0
    w = st.get("win") or {}; land = max(1, w.get("landTiles") or 1); thr = (w.get("thresholdTenths") or 800) / 1000.0
    return min(1.2, st["self"]["tiles"] / (land * thr))


class VecEnv2:
    def __init__(self, n, cfg_fn, max_steps=1500, decide_every=20):
        self.n, self.cfg_fn, self.max_steps = n, cfg_fn, max_steps
        self.sess = [Session(decide_every, max_steps) for _ in range(n)]; self.counter = 0
        self.pool = ThreadPoolExecutor(max_workers=n); self.pot = [0.0] * n; self.ep_ret = [0.0] * n; self.steps = [0] * n
        self.obs = list(self.pool.map(self._start, range(n)))

    def _start(self, i):
        self.counter += 1; cfg = self.cfg_fn(); sess = self.sess[i]
        o = sess.start(cfg, cfg.get("_seed") or f"w{self.counter:08d}"); sess.cfg = cfg; self.pot[i] = 0.0; self.ep_ret[i] = 0.0; self.steps[i] = 0
        return o

    def _one(self, i, actions):
        sess = self.sess[i]; was_spawn = bool(sess.last["state"].get("spawnPhase"))
        r = sess.apply(actions); self.steps[i] += 1; st = r["state"]; ended = None; win = False
        if not r["ok"]: ended = "engine_error"
        if was_spawn and not ended:
            sess.spawn_wait(); st = sess.last["state"]; r = sess.last
            if "self" not in st: ended = "spawn_failed"
        alive = "self" in st and st["self"]["alive"]
        wid = r.get("winner"); me = st["self"]["id"] if "self" in st else None
        if wid is not None: win = (wid == me); ended = "win" if win else "loss_winner_other"
        elif not alive and not st.get("spawnPhase"): ended = "dead"
        elif self.steps[i] >= self.max_steps: ended = "timeout"
        pot = potential(st) if not st.get("spawnPhase") else 0.0
        rew = SHAPE * (pot - self.pot[i]) + (WIN_R if win else LOSS_R if ended in ("dead", "loss_winner_other") else 0.0)
        self.pot[i] = pot; self.ep_ret[i] += rew; info = None
        if ended:
            info = {"end": ended, "win": win, "ret": self.ep_ret[i], "steps": self.steps[i], "cfg": sess.cfg, "tick": r["tick"], "progress": pot}
            if ended == "engine_error":
                sess.close(); self.sess[i] = Session(sess.de, sess.max_steps)
            return rew, True, info, self._start(i)
        return rew, False, None, sess.observe()

    def step(self, actions_list):
        res = list(self.pool.map(lambda a: self._one(*a), list(enumerate(actions_list))))
        self.obs = [r[3] for r in res]
        return [r[0] for r in res], [r[1] for r in res], [r[2] for r in res]

    def close(self):
        for s in self.sess: s.close()
        self.pool.shutdown(wait=False)
