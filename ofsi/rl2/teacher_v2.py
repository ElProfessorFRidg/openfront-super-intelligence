"""Professeur v2 dans l'espace d'actions hierarchique. Heuristique scriptee (amorcage/baseline), JAMAIS un plafond pour l'eleve.
Ne choisit que des (type, pointeur) autorises par les masques exacts ; retourne jusqu'a M_SUB actions (type, indice_banque, parametre)."""
import random
import numpy as np
from ofsi.rl2 import space as S

T = S.T
SEND_P, EXPAND_P = 3, 2          # indices de FRACS : 0.50 et 0.30


class TeacherV2:
    name = "teacher_v2"

    def __init__(self, seed=0, ratio=1.5, naval=True, diplomacy=True, nuke=True, city_per_tiles=3500, reserve=0.3, send=3, expand=2, defend=0.5, ally_mode="none", ally_ratio=0.6):
        self.rng = random.Random(seed); self.ratio, self.naval, self.diplomacy, self.nuke, self.cpt = ratio, naval, diplomacy, nuke, city_per_tiles
        self.reserve, self.send, self.expand, self.defend = reserve, send, expand, defend
        self.ally_mode, self.ally_ratio, self.asked = ally_mode, ally_ratio, {}      # ally_mode: none | threats (joueurs >= ally_ratio x mes troupes) | all      # reserve = fraction de maxTroops gardee ; send/expand = indices de FRACS
        self.hist, self.i, self.last_boat = [], 0, -10**9

    def _slots(self, obs, t):
        pm = obs["ptr_mask"][T[t]]
        return np.flatnonzero(pm)

    def act(self, obs, st, costs, cands):
        """Retourne liste [(type, ptr, param), ...] (STOP implicite a la fin)."""
        self.i += 1
        tm, out = obs["type_mask"], []
        if st.get("spawnPhase"):
            if tm[T["SPAWN"]]:                       # spawn : masse la plus grande, tuile au hasard
                sl = self._slots(obs, "SPAWN"); sp = cands["spawn"]
                best = max(sl, key=lambda j: (sp[j - S.OFF["spawn"][0]][2], self.rng.random()))
                return [(T["SPAWN"], int(best), 0)]
            return []
        s = st["self"]; troops, mx, gold = s["troops"], max(1, s["maxTroops"]), s["gold"]; u = s["units"]
        self.hist.append(s["tiles"]); stalled = len(self.hist) > 6 and (self.hist[-1] - self.hist[-6]) / max(1, self.hist[-6]) < 0.01
        threat = sum(a["troops"] for a in st["incomingAttacks"] if not a["retreating"]); spare = troops - 1.2 * threat
        pl = st["players"]; po = S.OFF["players"][0]

        def add(t, ptr=0, par=0):
            if tm[T[t]] and all(x[0] != T[t] for x in out) and len(out) < S.M_SUB: out.append((T[t], int(ptr), int(par))); return True
            return False

        # 0. alliances proactives (mesure A/B) : les tribus acceptent 5/5 ; une alliance expire apres 5 min sans penalite
        if self.ally_mode != "none" and tm[T["ALLY_REQUEST"]]:
            for j in self._slots(obs, "ALLY_REQUEST"):
                p = pl[j - po]
                if not p["canAlly"] or self.i - self.asked.get(p["id"], -10**9) < 160: continue
                if self.ally_mode == "all" or p["troops"] >= self.ally_ratio * troops:
                    self.asked[p["id"]] = self.i
                    if add("ALLY_REQUEST", j): break
        # 1. diplomatie : accepter une demande venant d'un joueur plus fort
        if self.diplomacy and tm[T["ALLY_REQUEST"]]:
            for j in self._slots(obs, "ALLY_REQUEST"):
                p = pl[j - po]
                if p["incomingRequest"] and p["troops"] > troops: add("ALLY_REQUEST", j); break
        # 2. guerre / expansion
        if spare > self.reserve * mx or troops > 0.8 * mx:
            tgt = None
            if tm[T["ATTACK_PLAYER"]]:
                sl = self._slots(obs, "ATTACK_PLAYER"); j = min(sl, key=lambda j: pl[j - po]["troops"])
                if troops > self.ratio * pl[j - po]["troops"]: tgt = j
            if tgt is not None: add("ATTACK_PLAYER", tgt, self.send)
            elif not stalled or self.i % 4 == 0: add("ATTACK_NEUTRAL", 0, self.expand)
        # 3. invasion navale
        if self.naval and stalled and tm[T["BOAT"]] and troops > 0.5 * mx and self.i - self.last_boat >= 5:
            sl = self._slots(obs, "BOAT"); bo = S.OFF["boat"][0]; bc = cands["boat"]
            ok = [j for j in sl if bc[j - bo]["owner"] is None or bc[j - bo]["ownerTroops"] < 0.8 * troops]
            if ok:
                j = min(ok, key=lambda j: (bc[j - bo]["owner"] is not None, bc[j - bo]["ownerTroops"], -bc[j - bo]["landmassSize"]))
                if add("BOAT", j, self.send): self.last_boat = self.i
        # 4. economie : une construction/amelioration par decision
        n_city, n_port, n_fac = u.get("City", 0), u.get("Port", 0), u.get("Factory", 0); want_city = 3 + s["tiles"] // self.cpt

        def build(kind, prefer=None):
            if not tm[T["BUILD_" + kind]]: return False
            sl = self._slots(obs, "BUILD_" + kind); o = S.OFF["tiles_" + kind][0]; c = cands["tiles_" + kind]
            if prefer: pref = [j for j in sl if c[j - o][prefer]]; sl = pref if len(pref) else sl
            return add("BUILD_" + kind, self.rng.choice(list(sl)))
        done = False
        if threat > self.defend * troops: done = build("Defense Post", "border")
        if not done and n_port == 0 and s["tiles"] > 4000: done = build("Port", "shore")
        if not done and n_city < want_city: done = build("City")
        if not done and n_city >= 3 and n_port > 0 and n_fac < max(1, n_port): done = build("Factory")
        if not done and n_port < 1 + s["tiles"] // 15000: done = build("Port", "shore")
        if not done and gold > 400000 and tm[T["UPGRADE"]]:
            sl = self._slots(obs, "UPGRADE"); uo = S.OFF["upgrade"][0]; uc = cands["upgrade"]
            j = min(sl, key=lambda j: uc[j - uo]["cost"][0]); add("UPGRADE", j)
        # 5. armes (si riche) : silo puis bombe sur le plus gros ennemi
        if self.nuke and gold > 2_500_000:
            if u.get("Missile Silo", 0) == 0: build("Missile Silo")
            elif self.i % 3 == 0 and tm[T["NUKE_Atom Bomb"]]:
                sl = self._slots(obs, "NUKE_Atom Bomb"); no = S.OFF["nuke"][0]; nc = cands["nuke"]; add("NUKE_Atom Bomb", max(sl, key=lambda j: nc[j - no]["ownerTiles"]))
        return out
