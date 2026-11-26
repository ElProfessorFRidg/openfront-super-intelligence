"""Detecteur automatique de stagnation / blocage / ressources inutilisees. Observe uniquement l'etat legitime de l'agent.
Chaque drapeau est une MESURE (fenetre glissante), jamais une supposition."""
from collections import deque


class StagnationDetector:
    def __init__(self, window=40):
        self.w = window
        self.tiles = deque(maxlen=window)
        self.troop_frac = deque(maxlen=window)
        self.gold = deque(maxlen=window)
        self.noborder = deque(maxlen=window)
        self.flags_time = {}

    def update(self, st, costs):
        s = st["self"]
        self.tiles.append(s["tiles"])
        self.troop_frac.append(s["troops"] / max(1, s["maxTroops"]))
        self.gold.append(s["gold"])
        self.noborder.append(not any(p["border"] for p in st["players"]))
        cheapest = min([c for k, c in costs.items() if c > 0] or [1e18])
        full = len(self.tiles) == self.w
        flags = {}
        if full:
            gain = (self.tiles[-1] - self.tiles[0]) / max(1, self.tiles[0])
            flags["territorial_stall"] = gain < 0.005                                   # <0,5 % de territoire sur la fenetre
            flags["troops_idle"] = min(self.troop_frac) > 0.9                          # troupes quasi au plafond tout le long
            flags["gold_hoard"] = min(self.gold) > 4 * cheapest                        # or > 4x l'objet le moins cher, tout le long
            flags["no_land_frontier"] = all(self.noborder)                             # aucun voisin terrestre
            flags["blocked"] = flags["territorial_stall"] and (flags["troops_idle"] or flags["gold_hoard"])
        for k, v in flags.items():
            self.flags_time[k] = self.flags_time.get(k, 0) + int(bool(v))
        return flags
