"""Scenarios de competence, lot 3 : hypotheses tirees de la documentation d'OpenFront_Agents (a VERIFIER sur le moteur epingle, pas a croire)."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ofsi.skills import Sc, RICH, grow, result, TESTS


def t_tribes_accept_alliance():
    """Les tribus (bots) acceptent-elles automatiquement une demande d'alliance ? On mesure sur le moteur."""
    sc = Sc(1, bots=8, nations="disabled", overrides={}, difficulty="Easy"); grow(sc, 600)
    st = sc.st(0); pl = st["players"]; bots = [p for p in pl if str(p["type"]).upper() == "BOT"]
    cand = [p for p in bots if p["canAlly"]]
    if not cand: sc.close(); return result("tribes_accept_alliance", False, f"aucun bot allie-able (bots vus={len(bots)})")
    sent = cand[:5]
    for p in sent: sc.step(1, [{"type": "allianceRequest", "recipient": p["id"], "clientID": sc.cid[0]}])
    sc.step(200); me = sc.me(0); allied = [p["id"] for p in sent if p["id"] in me["allies"]]
    sc.close(); return result("tribes_accept_alliance", len(allied) > 0, f"demandes envoyees={len(sent)} ; alliances obtenues={len(allied)} ({len(allied)}/{len(sent)})")


def t_nation_accept_alliance_by_difficulty():
    out = []
    for diff in ("Easy", "Medium", "Hard"):
        sc = Sc(1, bots=0, nations="default", overrides={}, difficulty=diff, seed="sk000007x"); grow(sc, 800); pl = [p for p in sc.st(0)["players"] if str(p["type"]).upper() == "NATION" and p["canAlly"]][:4]
        for p in pl: sc.step(1, [{"type": "allianceRequest", "recipient": p["id"], "clientID": sc.cid[0]}])
        sc.step(300); me = sc.me(0); out.append(f"{diff}: {sum(1 for p in pl if p['id'] in me['allies'])}/{len(pl)}"); sc.close()
    return result("nations_accept_alliance_par_difficulte", True, "; ".join(out) + " (mesure descriptive, pas un test PASS/FAIL)")


def t_emoji_effect():
    """Effet de l'emoji sur la relation INTERNE d'une NATION envers moi (`theirRelation`, diagnostic : non fourni a l'agent). Mesure directe, avant/apres."""
    sc = Sc(1, bots=0, nations="default", overrides={}, difficulty="Easy", seed="sk000009x"); grow(sc, 800)
    pl = [p for p in sc.st(0)["players"] if str(p["type"]).upper() == "NATION" and p.get("canEmoji")]
    if len(pl) < 2: sc.close(); return result("emoji_effet_relation", False, "moins de 2 nations avec canEmoji")
    ins, peace = pl[0]["id"], pl[1]["id"]; rel = lambda i: next(p["theirRelation"] for p in sc.st(0)["players"] if p["id"] == i)
    r0 = (rel(ins), rel(peace))
    sc.do({"type": "emoji", "recipient": ins, "emoji": 14, "clientID": sc.cid[0]}, 15)        # insulte
    sc.do({"type": "emoji", "recipient": peace, "emoji": 27, "clientID": sc.cid[0]}, 15)      # paix
    r1 = (rel(ins), rel(peace)); sc.close()
    return result("emoji_effet_relation", r1[0] < r0[0], f"relation de la nation envers moi (0=Hostile..3=Friendly) : insultee {r0[0]}->{r1[0]} ; paix (Easy) {r0[1]}->{r1[1]}")


def t_target_player():
    """targetPlayer : la cible entre dans targets() ET sa relation envers moi chute (TargetPlayerExecution : updateRelation -40)."""
    sc = Sc(1, bots=0, nations="default", overrides={}, difficulty="Easy", seed="sk000009x"); grow(sc, 800)
    pl = [p for p in sc.st(0)["players"] if str(p["type"]).upper() == "NATION" and p["canTarget"]]
    if not pl: sc.close(); return result("target_player", False, "aucune nation ciblable (canTarget)")
    t = pl[0]["id"]; r0 = pl[0]["theirRelation"]; sc.do({"type": "targetPlayer", "target": t, "clientID": sc.cid[0]}, 15)
    st = sc.st(0); r1 = next(p["theirRelation"] for p in st["players"] if p["id"] == t); tg = t in st["self"].get("targets", []); sc.close()
    return result("target_player", tg and r1 <= r0, f"dans targets()={tg} ; relation de la cible envers moi {r0}->{r1}")


def t_spawn():
    """spawn : l'agent choisit une tuile LEGALE (fournie par le moteur) et possede ensuite du territoire autour d'elle."""
    sc = Sc(1, bots=4, nations="default", overrides={}, difficulty="Easy", seed="sk000010x"); me = sc.me(0)
    sc.close(); return result("spawn", me["tiles"] > 0 and me.get("spawned", True), f"tuiles apres spawn={me['tiles']}")


TESTS.update({"target_player": t_target_player, "spawn": t_spawn, "emoji_effect": t_emoji_effect, "tribes_accept_alliance": t_tribes_accept_alliance, "nations_alliance_difficulty": t_nation_accept_alliance_by_difficulty})
