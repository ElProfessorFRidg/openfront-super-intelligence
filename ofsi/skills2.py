"""Scenarios de competence, lot 2 : armes (H, MIRV), interception SAM, navires de guerre, annulation de bateau, diplomatie, embargo global, commerce, trains.
Meme regle que skills.py : effet observable verifie dans l'etat reel ; surcharges de config reservees aux scenarios."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ofsi.skills import Sc, RICH, grow, result, TESTS


def _two(gap=140, seed="sk000002x", **kw):
    sc = Sc(2, gap=gap, overrides=RICH, seed=seed, **kw)
    for _ in range(12):
        for i in (0, 1):
            sc.step(1, [{"type": "attack", "targetID": None, "troops": int(sc.me(i)["troops"] * 0.3), "clientID": sc.cid[i]}])
        sc.step(30)
    return sc


def _build_enemy_city(sc):
    c1 = sc.e.cands("build", unit="City", max=4, agent=1)
    sc.step(1, [{"type": "build_unit", "unit": "City", "tile": c1[0]["tile"], "clientID": sc.cid[1]}])
    sc.step(60)
    return c1[0]["tile"]


def _launch(sc, unit):
    s0 = sc.e.cands("build", unit="Missile Silo", max=4)
    sc.do({"type": "build_unit", "unit": "Missile Silo", "tile": s0[0]["tile"], "clientID": sc.cid[0]}, 80)
    tg = sc.e.cands("nuke", unit=unit, max=16)
    if not tg:
        return None
    sc.do({"type": "build_unit", "unit": unit, "tile": tg[0]["tile"], "clientID": sc.cid[0]}, 5)
    for _ in range(80):
        sc.step(10)
    return tg[0]


def t_nuke_hydrogen():
    sc = _two()
    _build_enemy_city(sc)
    c0, t0 = sc.me(1)["units"].get("City", 0), sc.me(1)["tiles"]
    tg = _launch(sc, "Hydrogen Bomb")
    if not tg:
        sc.close()
        return result("nuke_hydrogen", False, "aucune cible legale")
    c1, t1 = sc.me(1)["units"].get("City", 0), sc.me(1)["tiles"]
    elim = sc.me(1).get("eliminated", False)
    sc.close()
    return result("nuke_hydrogen", c1 < c0 and t1 < t0, f"villes {c0}->{c1}; tuiles ennemies {t0}->{t1} (perte {t0 - t1}); ennemi elimine={elim}")


def t_nuke_mirv():
    sc = _two()
    _build_enemy_city(sc)
    c0, t0 = sc.me(1)["units"].get("City", 0), sc.me(1)["tiles"]
    tg = _launch(sc, "MIRV")
    if not tg:
        sc.close()
        return result("nuke_mirv", False, "aucune cible legale")
    c1, t1 = sc.me(1)["units"].get("City", 0), sc.me(1)["tiles"]
    sc.close()
    return result("nuke_mirv", c1 < c0 or t1 < t0, f"villes {c0}->{c1}; tuiles ennemies {t0}->{t1} (perte {t0 - t1})")


def t_sam_intercept():
    """Meme frappe atomique avec et sans SAM a cote de la ville ennemie : avec SAM, la ville doit survivre."""
    out = {}
    for with_sam in (False, True):
        sc = _two(seed="sk000003x")
        ct = _build_enemy_city(sc)
        if with_sam:
            c = sc.e.cands("build", unit="SAM Launcher", max=16, agent=1)
            near = sorted(c, key=lambda x: abs(x["tile"] - ct))[:1]
            sc.step(1, [{"type": "build_unit", "unit": "SAM Launcher", "tile": near[0]["tile"], "clientID": sc.cid[1]}])
            sc.step(80)
        c0 = sc.me(1)["units"].get("City", 0)
        sam = sc.me(1)["units"].get("SAM Launcher", 0)
        tg = _launch(sc, "Atom Bomb")
        out[with_sam] = (c0, sc.me(1)["units"].get("City", 0), sam, bool(tg))
        sc.close()
    (a0, a1, _, ok0), (b0, b1, sam, ok1) = out[False], out[True]
    return result("sam_intercept", ok0 and ok1 and a1 < a0 and b1 >= b0 and sam >= 1, f"sans SAM: villes {a0}->{a1}; avec SAM({sam}): villes {b0}->{b1}")


def t_warship():
    sc = Sc(1, overrides=RICH)
    grow(sc, 800)
    pc = [x for x in sc.e.cands("build", unit="Port", max=8) if x["shore"]]
    if not pc:
        sc.close()
        return result("warship_build_move", False, "pas de tuile de port cotiere")
    sc.do({"type": "build_unit", "unit": "Port", "tile": pc[0]["tile"], "clientID": sc.cid[0]}, 60)
    w = sc.e.cands("warship", max=8)
    if not w:
        sc.close()
        return result("warship_build_move", False, "aucune zone de patrouille legale")
    sc.do({"type": "build_unit", "unit": "Warship", "tile": w[0]["tile"], "clientID": sc.cid[0]}, 60)
    ws = [u for u in sc.st(0)["units"] if u["type"] == "Warship"]
    if not ws:
        sc.close()
        return result("warship_build_move", False, "Warship non cree")
    u = ws[0]
    far = max(w, key=lambda c: abs(c["tile"] - w[0]["tile"]))
    sc.do({"type": "move_warship", "unitIds": [u["id"]], "tile": far["tile"], "clientID": sc.cid[0]}, 5)
    for _ in range(30):
        sc.step(20)
    u2 = [x for x in sc.st(0)["units"] if x["id"] == u["id"]]
    sc.close()
    moved = bool(u2) and (u2[0]["x"], u2[0]["y"]) != (u["x"], u["y"])
    return result("warship_build_move", moved, f"warship id={u['id']} ({u['x']},{u['y']}) -> {(u2[0]['x'], u2[0]['y']) if u2 else 'detruit'}")


def t_cancel_boat():
    sc = Sc(1)
    grow(sc, 1200)
    me = sc.me(0)
    sizes, h = sc.e.landmasses([sc.spawns[0]])
    c = [x for x in sc.e.cands("boat", max=24) if x["landmass"] != h[0]]
    if not c:
        sc.close()
        return result("cancel_boat", False, "aucun candidat naval")
    t0 = me["tiles"]
    sc.do({"type": "boat", "dst": c[0]["tile"], "troops": int(me["troops"] * 0.5), "clientID": sc.cid[0]}, 8)
    b = [u for u in sc.st(0)["units"] if u["type"] == "Transport"]
    if not b:
        sc.close()
        return result("cancel_boat", False, "bateau absent apres envoi")
    sc.do({"type": "cancel_boat", "unitID": b[0]["id"], "clientID": sc.cid[0]}, 5)
    for _ in range(80):
        sc.step(20)
    f = sc.me(0)
    sc.close()
    return result("cancel_boat", f["boats"] == 0 and f["tiles"] < t0 + 400, f"bateau {b[0]['id']} annule ; restants={f['boats']} ; tuiles {t0}->{f['tiles']} (un debarquement aurait donne > +1000)")


def t_alliance_reject():
    sc = _two()
    p0, p1 = sc.me(0)["id"], sc.me(1)["id"]
    sc.do({"type": "allianceRequest", "recipient": p1, "clientID": sc.cid[0]}, 5)
    had = p0 in sc.me(1)["incomingAllianceRequests"]
    sc.do({"type": "allianceReject", "requestor": p0, "clientID": sc.cid[1]}, 10)
    still = p0 in sc.me(1)["incomingAllianceRequests"]
    allied = p1 in sc.me(0)["allies"]
    sc.close()
    return result("alliance_reject", had and not still and not allied, f"demande recue={had}; apres rejet: encore presente={still}; allies={allied}")


def t_embargo_all():
    sc = _two()
    before = sc.me(0)["canEmbargoAll"]
    sc.do({"type": "embargo_all", "action": "start", "clientID": sc.cid[0]}, 5)
    pl = sc.st(0)["players"]
    allemb = bool(pl) and all(p["embargoedByMe"] for p in pl)
    after = sc.me(0)["canEmbargoAll"]
    sc.close()
    return result("embargo_all", before and allemb, f"canEmbargoAll avant={before}, apres={after} ; tous embargos={allemb}")


def t_trade():
    sc = _two(gap=90)
    for _ in range(40):   # croissance supplementaire : les deux agents doivent atteindre une cote
        for i in (0, 1):
            sc.step(1, [{"type": "attack", "targetID": None, "troops": int(sc.me(i)["troops"] * 0.3), "clientID": sc.cid[i]}])
        sc.step(30)
    for i in (0, 1):
        pc = [x for x in sc.e.cands("build", unit="Port", max=16, probe=600, agent=i) if x["shore"]]
        if pc:
            sc.step(1, [{"type": "build_unit", "unit": "Port", "tile": pc[0]["tile"], "clientID": sc.cid[i]}])
    for _ in range(300):
        sc.step(20)
    m = [sc.me(i) for i in (0, 1)]
    ev = f"ports={[x['units'].get('Port', 0) for x in m]} navires={[x['units'].get('Trade Ship', 0) for x in m]} tradeGold={[x['tradeGold'] for x in m]} partenaires={[x['tradingPartners'] for x in m]}"
    sc.close()
    return result("trade_maritime", any(x["tradeGold"] > 0 for x in m), ev)


def t_trains():
    sc = Sc(1, overrides=RICH)
    grow(sc, 1500)
    for u, n in (("City", 3), ("Factory", 2), ("Port", 1)):
        for _ in range(n):
            c = sc.e.cands("build", unit=u, max=8)
            if u == "Port":
                c = [x for x in c if x["shore"]] or c
            if c:
                sc.step(1, [{"type": "build_unit", "unit": u, "tile": c[0]["tile"], "clientID": sc.cid[0]}])
                sc.step(30)
    for _ in range(120):
        sc.step(20)
    m = sc.me(0)
    ev = f"unites={m['units']} trainGold={m['trainGold']} tradeGold={m['tradeGold']}"
    sc.close()
    return result("trade_trains", m["trainGold"] > 0, ev)


TESTS.update({"nuke_hydrogen": t_nuke_hydrogen, "nuke_mirv": t_nuke_mirv, "sam_intercept": t_sam_intercept, "warship": t_warship, "cancel_boat": t_cancel_boat,
              "alliance_reject": t_alliance_reject, "embargo_all": t_embargo_all, "trade": t_trade, "trains": t_trains})
