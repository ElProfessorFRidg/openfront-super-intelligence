"""Professeur v2 : utilise TOUTES les mecaniques de gameplay (expansion, conquete, invasion navale, economie, ameliorations,
defense, diplomatie, armes). Heuristique scriptee : sert d'amorcage et de baseline, JAMAIS de plafond pour l'eleve."""
import random


class Teacher2:
    name = "teacher2"

    def __init__(self, cid, env, seed=0, p=None):
        self.cid, self.env, self.rng = cid, env, random.Random(seed)
        self.p = dict(ratio=1.5, send=0.5, expand=0.3, boat_send=0.5, reserve=0.35, city_per_tiles=3500, nuke=True, diplomacy=True, naval=True, **(p or {}))
        self.hist = []          # tiles par decision
        self.last_boat = -10**9
        self.step_i = 0
        self.log = {}           # compteurs d'actions emises

    def _emit(self, kind, intent, out):
        self.log[kind] = self.log.get(kind, 0) + 1
        out.append(intent)

    def act(self, st, costs, tick):
        self.step_i += 1
        s = st["self"]
        if not s["alive"]:
            return []
        out, gold, troops, mx = [], s["gold"], s["troops"], max(1, s["maxTroops"])
        cid, p = self.cid, self.p
        self.hist.append(s["tiles"])
        stalled = len(self.hist) > 6 and (self.hist[-1] - self.hist[-6]) / max(1, self.hist[-6]) < 0.01
        units = s["units"]
        nb = [q for q in st["players"] if q["border"] and q["canAttack"] and not q["allied"]]

        # --- defense / retraite : attaque entrante forte -> garder les troupes, bloquer les gros envois
        threat = sum(a["troops"] for a in st["incomingAttacks"] if not a["retreating"])
        spare = troops - 1.2 * threat

        # --- diplomatie : accepter les demandes entrantes d'un joueur plus fort ; ne jamais s'allier avec un voisin faible
        if p["diplomacy"]:
            for q in st["players"]:
                if q["incomingRequest"] and q["canAlly"] and q["troops"] > troops:
                    self._emit("ally_accept", {"type": "allianceRequest", "recipient": q["id"], "clientID": cid}, out)
                    break

        # --- guerre terrestre : voisin le plus faible si superiorite nette, sinon expansion sur terre neutre
        if spare > 0.3 * mx or troops > 0.8 * mx:
            tgt = min(nb, key=lambda q: q["troops"]) if nb else None
            if tgt and troops > p["ratio"] * tgt["troops"]:
                self._emit("attack_player", {"type": "attack", "targetID": tgt["id"], "troops": int(max(0, spare) * p["send"]), "clientID": cid}, out)
            elif not stalled or self.step_i % 4 == 0:
                self._emit("attack_neutral", {"type": "attack", "targetID": None, "troops": int(max(0, spare) * p["expand"]), "clientID": cid}, out)

        # --- invasion navale : quand l'expansion terrestre est bloquee
        if p["naval"] and stalled and s["boats"] < s["boatsMax"] and troops > 0.5 * mx and self.step_i - self.last_boat >= 5:
            cands = self.env.cands("boat", max=24)
            def key(c):                       # neutre d'abord, puis proprietaire le plus faible, grande masse preferee
                return (c["owner"] is not None, c["ownerTroops"], -c["landmassSize"])
            ok = [c for c in cands if c["owner"] is None or c["ownerTroops"] < 0.8 * troops]
            if ok:
                c = min(ok, key=key)
                self._emit("boat", {"type": "boat", "dst": c["tile"], "troops": int(troops * p["boat_send"]), "clientID": cid}, out)
                self.last_boat = self.step_i

        # --- economie : une construction ou amelioration par decision, par priorite
        n_city, n_port, n_fac = units.get("City", 0), units.get("Port", 0), units.get("Factory", 0)
        build = None
        want_city = 3 + s["tiles"] // p["city_per_tiles"]
        if threat > 0.5 * troops and gold >= costs.get("Defense Post", 1e18):
            build = "Defense Post"
        elif n_port == 0 and gold >= costs.get("Port", 1e18) and s["tiles"] > 4000:
            build = "Port"
        elif n_city < want_city and gold >= costs.get("City", 1e18):
            build = "City"
        elif n_city >= 3 and n_fac < max(1, n_port) and gold >= costs.get("Factory", 1e18) and n_port > 0:
            build = "Factory"
        elif n_port < 1 + s["tiles"] // 15000 and gold >= costs.get("Port", 1e18):
            build = "Port"
        if build:
            c = self.env.cands("build", unit=build, max=12)
            if build == "Port":
                c = [x for x in c if x["shore"]] or c
            if build == "Defense Post":
                c = [x for x in c if x["border"]] or c
            if c:
                self._emit("build_" + build, {"type": "build_unit", "unit": build, "tile": self.rng.choice(c)["tile"], "clientID": cid}, out)
        elif gold > 400000:
            up = self.env.cands("upgrade")
            up = [u for u in up if u["cost"] and gold >= u["cost"][0] * 1.2]
            if up:
                u = min(up, key=lambda x: x["cost"][0])
                self._emit("upgrade", {"type": "upgrade_structure", "unit": u["type"], "unitId": u["id"], "amount": 1, "clientID": cid}, out)

        # --- armes : silo puis bombe sur les structures du plus gros ennemi (uniquement si riche)
        if p["nuke"] and gold > 2_500_000:
            if units.get("Missile Silo", 0) == 0 and gold >= costs.get("Missile Silo", 1e18):
                c = self.env.cands("build", unit="Missile Silo", max=6)
                if c:
                    self._emit("build_Missile Silo", {"type": "build_unit", "unit": "Missile Silo", "tile": c[0]["tile"], "clientID": cid}, out)
            elif units.get("Missile Silo", 0) > 0 and self.step_i % 3 == 0:
                c = self.env.cands("nuke", unit="Atom Bomb", max=8)
                if c:
                    t = max(c, key=lambda x: x["ownerTiles"])
                    self._emit("nuke", {"type": "build_unit", "unit": "Atom Bomb", "tile": t["tile"], "clientID": cid}, out)
        return out[:3]
