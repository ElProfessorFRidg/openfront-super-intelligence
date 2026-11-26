"""Scenarios de competence MECANIQUE par MECANIQUE. Chaque test emet l'intent du moteur et verifie un effet observable dans l'etat reel.
Les surcharges de config (or infini, construction instantanee) sont reservees a ces scenarios (jamais a l'entrainement/evaluation).
Un test PASS prouve que l'action est executable et a l'effet attendu ; il ne prouve PAS que l'agent sait bien l'utiliser (autre mesure)."""
import sys, json, time, pathlib, random, traceback
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ofsi.client import OFEnvProc

RICH = {"infiniteGold": True, "instantBuild": True}


class Sc:
    """Mini-harnais : 1 a 2 agents, spawn sur la plus grande masse, avec ecart controle entre les deux."""
    def __init__(self, agents=1, bots=0, overrides=None, map="Onion", seed="sk000001x", gap=60, difficulty="Easy", nations="disabled"):
        self.e = OFEnvProc()
        r = self.e.reset(map=map, seed=seed, agents=agents, bots=bots, difficulty=difficulty, nations=nations, overrides=overrides or {})
        self.cid = r["agentIds"]; self.n = agents
        c = self.e.spawn_candidates(stride=8); sizes, of = self.e.landmasses(c)
        big = max(range(len(sizes)), key=lambda i: sizes[i]); pool = [t for t, m in zip(c, of) if m == big]
        W = r["mapW"]; xy = lambda t: (t % W, t // W)
        a = pool[len(pool) // 2]; self.spawns = [a]
        if agents > 1:
            ax, ay = xy(a); b = min((t for t in pool if t != a), key=lambda t: abs(abs(xy(t)[0] - ax) + abs(xy(t)[1] - ay) - gap))
            self.spawns.append(b)
        self.s = self.e.step_state(1, [{"type": "spawn", "tile": self.spawns[i], "clientID": self.cid[i]} for i in range(agents)])
        while self.s["state"]["spawnPhase"]: self.s = self.e.step_state(1)

    def st(self, i=0): return self.e.state2(i)["state"] if i else self.s["state"]
    def me(self, i=0):
        st = self.e.state2(i)["state"]
        return st.get("self") or {"alive": False, "eliminated": True, "id": None, "tiles": 0, "units": {}, "gold": 0, "troops": 0, "boats": 0, "allies": [], "incomingAllianceRequests": [],
                                   "tradeGold": 0, "trainGold": 0, "tradingPartners": 0, "canEmbargoAll": False, "traitor": False}
    def step(self, ticks=1, intents=None):
        self.s = self.e.step_state(ticks, intents or []); return self.s
    def do(self, intent, ticks=20): return self.step(ticks, [intent])
    def close(self): self.e.close()


def grow(sc, ticks=1500, frac=0.4):
    for _ in range(ticks // 40):
        me = sc.me(0); sc.step(40, [{"type": "attack", "targetID": None, "troops": int(me["troops"] * frac), "clientID": sc.cid[0]}])


def result(name, passed, evidence): return {"skill": name, "passed": bool(passed), "evidence": evidence}


# ---------------- tests ----------------
def t_attack_neutral():
    sc = Sc(1); a = sc.me(0)["tiles"]; grow(sc, 400); b = sc.me(0)["tiles"]; sc.close()
    return result("attack_neutral", b > 1.5 * a, f"tuiles {a} -> {b}")

def t_attack_player():
    sc = Sc(2, gap=70, overrides=RICH)
    for _ in range(25):
        for i in (0, 1):
            me = sc.me(i); sc.step(1, [{"type": "attack", "targetID": None, "troops": int(me["troops"] * 0.3), "clientID": sc.cid[i]}])
        sc.step(30)
    s0, s1 = sc.me(0), sc.me(1); p1 = s1["id"]; border = any(p["id"] == p1 and p["border"] for p in sc.st(0)["players"])
    t0, t1 = s0["tiles"], s1["tiles"]
    for _ in range(30):
        sc.step(20, [{"type": "attack", "targetID": p1, "troops": int(sc.me(0)["troops"] * 0.8), "clientID": sc.cid[0]}])
    n0, n1 = sc.me(0)["tiles"], sc.me(1)["tiles"] if sc.st(1).get("self", {}).get("alive") else 0; sc.close()
    return result("attack_player", border and n0 > t0 and n1 < t1, f"frontiere={border}; agent0 {t0}->{n0}; agent1 {t1}->{n1}")

def t_boat():
    sc = Sc(1); grow(sc, 1200); me = sc.me(0)
    sizes, of0 = sc.e.landmasses([sc.spawns[0]]); home = of0[0]
    cands = sc.e.cands("boat", max=24); other = [c for c in cands if c["landmass"] != home]
    if not other: sc.close(); return result("boat", False, f"aucun candidat hors masse d'origine (candidats={len(cands)})")
    c = other[0]; t0 = me["tiles"]; sc.do({"type": "boat", "dst": c["tile"], "troops": int(me["troops"] * 0.5), "clientID": sc.cid[0]}, 10)
    boats = sc.me(0)["boats"]
    for _ in range(80): sc.step(20)
    f = sc.me(0); sc.close()
    return result("boat", boats >= 1 and f["tiles"] > t0 + 200, f"bateaux apres envoi={boats}; tuiles {t0}->{f['tiles']}; cible masse {c['landmass']} (taille {c['landmassSize']})")

def _build_test(unit, extra_check=None):
    sc = Sc(1, overrides=RICH); grow(sc, 600)
    c = sc.e.cands("build", unit=unit, max=8)
    if unit == "Port": c = [x for x in c if x["shore"]] or c
    if not c: sc.close(); return result("build_" + unit, False, "aucun candidat legal (verifie par le moteur)")
    n0 = sc.me(0)["units"].get(unit, 0); sc.do({"type": "build_unit", "unit": unit, "tile": c[0]["tile"], "clientID": sc.cid[0]}, 60)
    n1 = sc.me(0)["units"].get(unit, 0); sc.close()
    return result("build_" + unit, n1 == n0 + 1, f"{unit}: {n0} -> {n1}")

def t_upgrade():
    sc = Sc(1, overrides=RICH); grow(sc, 600); c = sc.e.cands("build", unit="City", max=4)
    sc.do({"type": "build_unit", "unit": "City", "tile": c[0]["tile"], "clientID": sc.cid[0]}, 60)
    up = sc.e.cands("upgrade")
    if not up: sc.close(); return result("upgrade_structure", False, "aucune amelioration legale apres construction")
    u = up[0]; sc.do({"type": "upgrade_structure", "unit": u["type"], "unitId": u["id"], "amount": 1, "clientID": sc.cid[0]}, 80)
    lv = [x for x in sc.st(0)["units"] if x["id"] == u["id"]]; sc.close()
    return result("upgrade_structure", bool(lv) and lv[0]["level"] > u["level"], f"niveau {u['level']} -> {lv[0]['level'] if lv else None}")

def t_delete_unit():
    sc = Sc(1, overrides=RICH); grow(sc, 600); c = sc.e.cands("build", unit="City", max=4)
    sc.do({"type": "build_unit", "unit": "City", "tile": c[0]["tile"], "clientID": sc.cid[0]}, 60)
    u = [x for x in sc.st(0)["units"] if x["type"] == "City"][0]; n0 = sc.me(0)["units"].get("City", 0)
    sc.do({"type": "delete_unit", "unitId": u["id"], "clientID": sc.cid[0]}, 5)
    n_mid = sc.me(0)["units"].get("City", 0)                     # marquee, pas encore supprimee (delai moteur)
    for _ in range(40): sc.step(20)
    n1 = sc.me(0)["units"].get("City", 0); sc.close()
    return result("delete_unit", n1 < n0, f"City {n0} -> (apres 5 ticks) {n_mid} -> (apres 800 ticks) {n1} ; suppression differee par le moteur (deletionMarkDuration)")

def t_cancel_attack():
    sc = Sc(2, gap=70, overrides=RICH)
    for _ in range(20):
        for i in (0, 1): sc.step(1, [{"type": "attack", "targetID": None, "troops": int(sc.me(i)["troops"] * 0.3), "clientID": sc.cid[i]}])
        sc.step(30)
    p1 = sc.me(1)["id"]; sc.do({"type": "attack", "targetID": p1, "troops": int(sc.me(0)["troops"] * 0.9), "clientID": sc.cid[0]}, 5)
    att = sc.st(0)["outgoingAttacks"]
    if not att: sc.close(); return result("cancel_attack", False, "aucune attaque sortante apres attaque (pas de frontiere ?)")
    sc.do({"type": "cancel_attack", "attackID": att[0]["id"], "clientID": sc.cid[0]}, 5); a2 = sc.st(0)["outgoingAttacks"]; ret = [a for a in a2 if a["id"] == att[0]["id"]]
    sc.step(100); a3 = [a for a in sc.st(0)["outgoingAttacks"] if a["id"] == att[0]["id"]]; sc.close()
    return result("cancel_attack", (ret and ret[0]["retreating"]) or not a3, f"attaque {att[0]['id']}: retreating={ret[0]['retreating'] if ret else 'termine'}; encore active apres 100 ticks={bool(a3)}")

def t_alliance():
    sc = Sc(2, gap=70, overrides=RICH)
    for _ in range(15):
        for i in (0, 1): sc.step(1, [{"type": "attack", "targetID": None, "troops": int(sc.me(i)["troops"] * 0.3), "clientID": sc.cid[i]}])
        sc.step(30)
    p0, p1 = sc.me(0)["id"], sc.me(1)["id"]; ev = []
    sc.do({"type": "allianceRequest", "recipient": p1, "clientID": sc.cid[0]}, 5); inc = sc.me(1)["incomingAllianceRequests"]; ev.append(f"demande recue={p0 in inc}")
    sc.do({"type": "allianceRequest", "recipient": p0, "clientID": sc.cid[1]}, 10); al = p1 in sc.me(0)["allies"] and p0 in sc.me(1)["allies"]; ev.append(f"allies={al}")
    ext = None
    if al:
        sc.do({"type": "allianceExtension", "recipient": p1, "clientID": sc.cid[0]}, 5); sc.do({"type": "allianceExtension", "recipient": p0, "clientID": sc.cid[1]}, 5); ext = "envoye"
        sc.do({"type": "breakAlliance", "recipient": p1, "clientID": sc.cid[0]}, 10); br = p1 not in sc.me(0)["allies"]; ev.append(f"rupture={br}; traitre={sc.me(0)['traitor']}"); ok = br
    else: ok = False
    sc.close(); return result("alliance_request_accept_break", al and ok, "; ".join(ev))

def t_donate():
    sc = Sc(2, gap=70, overrides=RICH)
    for _ in range(15):
        for i in (0, 1): sc.step(1, [{"type": "attack", "targetID": None, "troops": int(sc.me(i)["troops"] * 0.3), "clientID": sc.cid[i]}])
        sc.step(30)
    p0, p1 = sc.me(0)["id"], sc.me(1)["id"]
    for i, o in ((0, p1), (1, p0)): sc.do({"type": "allianceRequest", "recipient": o, "clientID": sc.cid[i]}, 5)
    pl = [p for p in sc.st(0)["players"] if p["id"] == p1]; ev = [f"canDonateGold={pl[0]['canDonateGold'] if pl else None}"]
    g0 = sc.me(1)["gold"]; tr0 = sc.me(1)["troops"]
    sc.do({"type": "donate_gold", "recipient": p1, "gold": 1000000, "clientID": sc.cid[0]}, 5); sc.do({"type": "donate_troops", "recipient": p1, "troops": 5000, "clientID": sc.cid[0]}, 5)
    g1 = sc.me(1)["gold"]; tr1 = sc.me(1)["troops"]; ev.append(f"or receveur {g0}->{g1}; troupes {tr0}->{tr1}"); sc.close()
    return result("donate_gold_troops", g1 > g0 or tr1 > tr0, "; ".join(ev) + " (or infini : l'or du receveur peut ne pas varier)")

def t_embargo():
    sc = Sc(2, gap=70, overrides=RICH); p1 = sc.me(1)["id"]; ev = []
    b = [p for p in sc.st(0)["players"] if p["id"] == p1][0]; ev.append(f"avant: embargoedByMe={b['embargoedByMe']} canEmbargo={b['canEmbargo']}")
    sc.do({"type": "embargo", "targetID": p1, "action": "start", "clientID": sc.cid[0]}, 5); a = [p for p in sc.st(0)["players"] if p["id"] == p1][0]; ev.append(f"apres: embargoedByMe={a['embargoedByMe']} canTrade={a['canTrade']}")
    sc.do({"type": "embargo", "targetID": p1, "action": "stop", "clientID": sc.cid[0]}, 5); c = [p for p in sc.st(0)["players"] if p["id"] == p1][0]; ev.append(f"retire: embargoedByMe={c['embargoedByMe']}")
    sc.close(); return result("embargo", (not b["embargoedByMe"]) and a["embargoedByMe"] and not c["embargoedByMe"], "; ".join(ev))

def t_nuke():
    sc = Sc(2, gap=140, overrides=RICH)
    for _ in range(12):
        for i in (0, 1): sc.step(1, [{"type": "attack", "targetID": None, "troops": int(sc.me(i)["troops"] * 0.3), "clientID": sc.cid[i]}])
        sc.step(30)
    c1 = sc.e.cands("build", unit="City", max=4, agent=1)
    sc.step(1, [{"type": "build_unit", "unit": "City", "tile": c1[0]["tile"], "clientID": sc.cid[1]}]); sc.step(60)
    s0 = sc.e.cands("build", unit="Missile Silo", max=4)
    sc.do({"type": "build_unit", "unit": "Missile Silo", "tile": s0[0]["tile"], "clientID": sc.cid[0]}, 80)
    tg = sc.e.cands("nuke", unit="Atom Bomb", max=16)
    if not tg: sc.close(); return result("nuke_atom", False, "aucune cible legale (silo hors portee ou pas de structure ennemie)")
    cities = sc.st(1)["self"]["units"].get("City", 0); tiles1 = sc.me(1)["tiles"]
    sc.do({"type": "build_unit", "unit": "Atom Bomb", "tile": tg[0]["tile"], "clientID": sc.cid[0]}, 5)
    for _ in range(60): sc.step(10)
    cities2 = sc.me(1)["units"].get("City", 0); tiles2 = sc.me(1)["tiles"]; sc.close()
    return result("nuke_atom", cities2 < cities or tiles2 < tiles1, f"cible={tg[0]['kind']}; villes ennemies {cities}->{cities2}; tuiles ennemies {tiles1}->{tiles2}")

TESTS = {"attack_neutral": t_attack_neutral, "attack_player": t_attack_player, "boat": t_boat, "build_City": lambda: _build_test("City"), "build_Port": lambda: _build_test("Port"),
         "build_Defense Post": lambda: _build_test("Defense Post"), "build_Factory": lambda: _build_test("Factory"), "build_SAM Launcher": lambda: _build_test("SAM Launcher"),
         "build_Missile Silo": lambda: _build_test("Missile Silo"), "upgrade_structure": t_upgrade, "delete_unit": t_delete_unit, "cancel_attack": t_cancel_attack,
         "alliance": t_alliance, "donate": t_donate, "embargo": t_embargo, "nuke_atom": t_nuke}

try:
    import ofsi.skills2  # enregistre le lot 2 dans TESTS
except Exception as _e:
    print("lot 2 indisponible:", _e)


def run_one(name):
    t = time.time()
    try: r = TESTS[name]()
    except Exception as ex: r = result(name, False, "EXCEPTION " + repr(ex)[:300] + " | " + traceback.format_exc()[-300:].replace("\n", " "))
    r["seconds"] = round(time.time() - t, 1); return r

if __name__ == "__main__":
    import multiprocessing as mp
    names = sys.argv[1].split(",") if len(sys.argv) > 1 else list(TESTS)
    with mp.Pool(min(8, len(names))) as pool: res = pool.map(run_one, names, chunksize=1)
    pathlib.Path("benchmarks/skills.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    for r in res: print(("PASS " if r["passed"] else "FAIL ") + r["skill"].ljust(30), r["evidence"][:250])
    print("PASS", sum(r["passed"] for r in res), "/", len(res))
