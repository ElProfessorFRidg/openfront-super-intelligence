"""Professeur v3 : TeacherV2 (alliances 'threats') + regles sensees pour les mecaniques que v2 n'utilisait jamais (SAM, navires de guerre, bombes H/MIRV, annulations,
embargo, extension/rupture d'alliance, ciblage, emoji, dons). Chaque regle est activable pour l'ablation. Il doit etre VALIDE en A/B contre v2 avant usage."""
import numpy as np
from ofsi.rl2 import space as S
from ofsi.rl2.teacher_v2 import TeacherV2

T = S.T
ALL_RULES = ("sam", "warship", "hbomb", "cancel", "embargo", "extend", "break", "target", "emoji", "donate")


class TeacherV3(TeacherV2):
    name = "teacher_v3"

    def __init__(self, seed=0, rules=ALL_RULES, **kw):
        kw.setdefault("ally_mode", "threats")
        super().__init__(seed=seed, **kw)
        self.rules = set(rules); self.last = {}

    def _gap(self, key, n):
        """Espacement minimal (en decisions) entre deux emissions d'une meme regle."""
        if self.i - self.last.get(key, -10**9) < n: return False
        self.last[key] = self.i; return True

    def act(self, obs, st, costs, cands):
        out = super().act(obs, st, costs, cands)
        if st.get("spawnPhase") or "self" not in st: return out
        tm = obs["type_mask"]; s = st["self"]; u = s["units"]; gold = s["gold"]; troops = s["troops"]; mx = max(1, s["maxTroops"]); pl = st["players"]; po = S.OFF["players"][0]
        used = {a[0] for a in out}

        def add(t, ptr=0, par=0):
            if len(out) < S.M_SUB and tm[T[t]] and T[t] not in used: out.append((T[t], int(ptr), int(par))); used.add(T[t]); return True
            return False
        slots = lambda t: np.flatnonzero(obs["ptr_mask"][T[t]])
        cities = [x for x in st["units"] if x["type"] == "City"]
        # SAM : une couverture pour 3 villes, placee au plus pres d'une ville (distance sur coordonnees normalisees)
        if "sam" in self.rules and tm[T["BUILD_SAM Launcher"]] and len(cities) >= 3 and u.get("SAM Launcher", 0) < len(cities) // 3 and gold > 1.3 * costs.get("SAM Launcher", 1e18) and self._gap("sam", 20):
            W, H = st["map"]["w"], st["map"]["h"]; o = S.OFF["tiles_SAM Launcher"][0]; c = cands["tiles_SAM Launcher"]; sl = slots("BUILD_SAM Launcher")
            tgt = cities[0]; j = min(sl, key=lambda j: (c[j - o]["x"] - tgt["x"] / W) ** 2 + (c[j - o]["y"] - tgt["y"] / H) ** 2); add("BUILD_SAM Launcher", j)
        # Navires de guerre : proteger le commerce quand on a >= 2 ports et de l'or
        if "warship" in self.rules and tm[T["BUILD_Warship"]] and u.get("Port", 0) >= 2 and u.get("Warship", 0) < 2 and gold > 2.0 * costs.get("Warship", 1e18) and self._gap("warship", 40):
            add("BUILD_Warship", slots("BUILD_Warship")[0])
        # Bombes : H si tres riche, MIRV si extremement riche (cible = le plus gros ennemi ayant des structures)
        if "hbomb" in self.rules and u.get("Missile Silo", 0) > 0 and self._gap("hbomb", 12):
            nc, no = cands.get("nuke", []), S.OFF["nuke"][0]
            for kind, need in (("NUKE_MIRV", 1.1 * costs.get("MIRV", 1e18)), ("NUKE_Hydrogen Bomb", 1.1 * costs.get("Hydrogen Bomb", 1e18))):
                if gold >= need and tm[T[kind]] and nc:
                    sl = slots(kind); add(kind, max(sl, key=lambda j: nc[j - no]["ownerTiles"])); break
        # Annulation d'attaque : sous forte menace et troupes basses, rappeler la plus grosse attaque sortante
        if "cancel" in self.rules and tm[T["CANCEL_ATTACK"]] and sum(a["troops"] for a in st["incomingAttacks"] if not a["retreating"]) > 0.7 * troops and troops < 0.4 * mx and self._gap("cancel", 6):
            sl = slots("CANCEL_ATTACK"); ao = S.OFF["myatt"][0]; add("CANCEL_ATTACK", max(sl, key=lambda j: st["outgoingAttacks"][j - ao]["troops"]))
        # Embargo : sur ceux qui m'embargo et ne sont pas allies (reciprocite)
        if "embargo" in self.rules and tm[T["EMBARGO_ON"]] and self._gap("embargo", 30):
            sl = [j for j in slots("EMBARGO_ON") if pl[j - po]["embargoesMe"] and not pl[j - po]["allied"]]
            if sl: add("EMBARGO_ON", sl[0])
        # Alliances : prolonger regulierement, rompre avec un allie nettement plus faible quand l'expansion est bloquee
        if "extend" in self.rules and tm[T["ALLY_EXTEND"]] and self._gap("extend", 100): add("ALLY_EXTEND", slots("ALLY_EXTEND")[0])
        stalled = len(self.hist) > 12 and (self.hist[-1] - self.hist[-12]) / max(1, self.hist[-12]) < 0.01
        if "break" in self.rules and stalled and tm[T["ALLY_BREAK"]] and troops > 0.6 * mx and self._gap("break", 60):
            sl = [j for j in slots("ALLY_BREAK") if pl[j - po]["troops"] * 2.0 < troops]
            if sl: add("ALLY_BREAK", min(sl, key=lambda j: pl[j - po]["troops"]))
        # Ciblage du plus gros ennemi non allie (baisse sa relation envers moi, informe les allies)
        if "target" in self.rules and tm[T["TARGET_PLAYER"]] and self._gap("target", 80):
            sl = [j for j in slots("TARGET_PLAYER") if not pl[j - po]["allied"]]
            if sl: add("TARGET_PLAYER", max(sl, key=lambda j: pl[j - po]["tiles"]))
        # Emoji de paix aux nations dont la relation n'est pas deja amicale (effet reel en Easy)
        if "emoji" in self.rules and tm[T["EMOJI"]] and self._gap("emoji", 50):
            sl = [j for j in slots("EMOJI") if str(pl[j - po]["type"]).upper() == "NATION" and pl[j - po]["relation"] <= 2 and not pl[j - po]["allied"]]
            if sl: add("EMOJI", sl[0], 0)
        # Dons : un peu d'or a un allie quand on est tres riche (renforce l'allie contre les menaces communes)
        if "donate" in self.rules and tm[T["DONATE_GOLD"]] and gold > 3_000_000 and self._gap("donate", 90):
            sl = [j for j in slots("DONATE_GOLD") if pl[j - po]["allied"]]
            if sl: add("DONATE_GOLD", sl[0], 0)
        return out
