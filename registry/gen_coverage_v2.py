"""Matrice de PREUVES v2, generee : intent du moteur -> type(s) d'action v2 -> scenario de competence -> resultat mesure -> demonstrations.
Rien n'est declare 'maitrise' : PASS = l'action s'execute avec l'effet attendu ; la maitrise par l'agent se mesure separement (evaluations)."""
import json, pathlib, sys, glob
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ofsi.rl2 import space as S

mech = json.loads((ROOT / "registry/mechanics.json").read_text(encoding="utf-8"))
# intent moteur -> (types d'action v2, scenarios de competence)
MAP = {
    "attack": (["ATTACK_NEUTRAL", "ATTACK_PLAYER"], ["attack_neutral", "attack_player"]), "boat": (["BOAT"], ["boat"]),
    "build_unit": (["BUILD_City", "BUILD_Port", "BUILD_Defense Post", "BUILD_Factory", "BUILD_SAM Launcher", "BUILD_Missile Silo", "BUILD_Warship", "NUKE_Atom Bomb", "NUKE_Hydrogen Bomb", "NUKE_MIRV"],
                   ["build_City", "build_Port", "build_Defense Post", "build_Factory", "build_SAM Launcher", "build_Missile Silo", "warship", "nuke_atom", "nuke_hydrogen", "nuke_mirv", "sam_intercept"]),
    "upgrade_structure": (["UPGRADE"], ["upgrade_structure"]), "delete_unit": (["DELETE_UNIT"], ["delete_unit"]), "cancel_attack": (["CANCEL_ATTACK"], ["cancel_attack"]), "cancel_boat": (["CANCEL_BOAT"], ["cancel_boat"]),
    "move_warship": (["MOVE_WARSHIPS"], ["warship"]), "spawn": (["SPAWN"], ["spawn"]), "allianceRequest": (["ALLY_REQUEST"], ["alliance", "tribes_accept_alliance"]), "allianceReject": (["ALLY_REJECT"], ["alliance_reject"]),
    "allianceExtension": (["ALLY_EXTEND"], ["alliance"]), "breakAlliance": (["ALLY_BREAK"], ["alliance"]), "targetPlayer": (["TARGET_PLAYER"], ["target_player"]), "donate_gold": (["DONATE_GOLD"], ["donate"]),
    "donate_troops": (["DONATE_TROOPS"], ["donate"]), "embargo": (["EMBARGO_ON", "EMBARGO_OFF"], ["embargo"]), "embargo_all": (["EMBARGO_ALL_ON", "EMBARGO_ALL_OFF"], ["embargo_all"]), "emoji": (["EMOJI"], ["emoji_effet_relation"]),
}
EXCLU = {"quick_chat": "texte pre-defini sans effet de jeu documente (les nations ignorent les Quick Chat)", "kick_player": "administration de lobby", "mark_disconnected": "administration", "toggle_pause": "administration",
         "update_game_config": "administration", "toggle_game_start_timer": "administration"}
res = {}
for f in ("skills_full.json",):
    p = ROOT / "benchmarks" / f
    if p.exists():
        for r in json.loads(p.read_text(encoding="utf-8")): res[r["skill"]] = r
alias = {"donate": "donate_gold_troops", "alliance": "alliance_request_accept_break", "trade": "trade_maritime", "trains": "trade_trains", "warship": "warship_build_move", "nuke_atom": "nuke_atom", "tribes_accept_alliance": "tribes_accept_alliance"}
demo = {}
dp = ROOT / "registry/demo_type_counts.json"
if dp.exists(): demo = json.loads(dp.read_text(encoding="utf-8"))
rows, cnt = [], {"valide": 0, "non_valide": 0, "sans_scenario": 0}
for name, f in mech["intents"].items():
    t = f.get("type", "").replace("literal:", "")
    if t in EXCLU: rows.append((t, "EXCLU", "-", "-", "-", EXCLU[t])); continue
    types, tests = MAP.get(t, ([], []))
    if not types: rows.append((t, "INCONNU", "-", "-", "-", "a classer")); continue
    out = []
    for k in tests:
        r = res.get(k) or res.get(alias.get(k, ""), None)
        out.append(f"{k}: " + ("PASS" if r and r["passed"] else ("FAIL" if r else "non execute")))
    ok = bool(tests) and all(("PASS" in o) for o in out)
    cnt["valide" if ok else ("sans_scenario" if not tests else "non_valide")] += 1
    d = ", ".join(f"{x}={demo.get(x, '?')}" for x in types[:4]) if demo else "(non mesure)"
    rows.append((t, "COUVERT v2", " ".join(types), "; ".join(out) if out else "AUCUN scenario", d, ""))
L = ["# Matrice de preuves des mecaniques (generee)", "", f"Moteur `{mech['engine_commit'][:8]}` ; espace d'actions v2 : {S.NT} types, banque de {S.NB} candidats. Resume intents de gameplay : {cnt}.", "",
     "| intent moteur | statut | types d'action v2 | scenarios de competence (effet verifie) | demonstrations (decisions) | note |", "|---|---|---|---|---|---|"]
L += [f"| {a} | {b} | {c} | {d} | {e} | {g} |" for a, b, c, d, e, g in rows]
(ROOT / "registry/coverage_v2.md").write_text("\n".join(L) + "\n", encoding="utf-8"); print("\n".join(L[:5]))
