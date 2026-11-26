"""Espace d'actions v2 : hierarchique (type -> pointeur vers candidat legal -> parametre), masquage dynamique exact, jusqu'a M actions/decision.
Couvre TOUS les intents de gameplay du moteur (voir registry/coverage.md). Les candidats et leur legalite viennent du moteur (cands.mts/state2.mts)."""
import math
import numpy as np

M_SUB = 3                                   # actions par decision (autoregressif, doublons de type interdits)
FRACS = np.array([0.05, 0.15, 0.30, 0.50, 0.80], dtype=np.float32)
TYPES = ["STOP", "ATTACK_NEUTRAL", "ATTACK_PLAYER", "BOAT", "BUILD_City", "BUILD_Port", "BUILD_Defense Post", "BUILD_Factory", "BUILD_SAM Launcher", "BUILD_Missile Silo",
         "UPGRADE", "NUKE_Atom Bomb", "NUKE_Hydrogen Bomb", "NUKE_MIRV", "BUILD_Warship", "MOVE_WARSHIPS", "CANCEL_ATTACK", "CANCEL_BOAT", "DELETE_UNIT",
         "ALLY_REQUEST", "ALLY_REJECT", "ALLY_EXTEND", "ALLY_BREAK", "TARGET_PLAYER", "DONATE_GOLD", "DONATE_TROOPS", "EMBARGO_ON", "EMBARGO_OFF",
         "EMBARGO_ALL_ON", "EMBARGO_ALL_OFF", "SPAWN", "EMOJI"]
NT = len(TYPES)
T = {n: i for i, n in enumerate(TYPES)}
PARAM_TYPES = {T["ATTACK_NEUTRAL"], T["ATTACK_PLAYER"], T["BOAT"], T["DONATE_GOLD"], T["DONATE_TROOPS"], T["EMOJI"]}
# EMOJI : le parametre choisit parmi les 5 emojis a EFFET DE JEU sur les nations (index plat dans emojiTable) : paix, coeur, applaudissements, clown (-10 relation), doigt d'honneur (-100)
EMOJI_IDX = [27, 48, 16, 11, 14]
USES_PARAM = np.zeros(NT, bool); USES_PARAM[list(PARAM_TYPES)] = True
NO_PTR = {T["STOP"], T["ATTACK_NEUTRAL"], T["EMBARGO_ALL_ON"], T["EMBARGO_ALL_OFF"]}
BUILD_KINDS = ["City", "Port", "Defense Post", "Factory", "SAM Launcher", "Missile Silo"]
UNIT_T = ["Transport", "Warship", "Port", "Atom Bomb", "Hydrogen Bomb", "Trade Ship", "Missile Silo", "Defense Post", "SAM Launcher", "City", "MIRV", "Train", "Factory"]
UPG_T = ["City", "Port", "Factory", "SAM Launcher", "Missile Silo"]
NUKE_T = ["Atom Bomb", "Hydrogen Bomb", "MIRV"]

# --- banque de candidats : un seul tenseur [NB, FC], domaines a offsets fixes ---
FC = 24
DOM = [("players", 24), ("boat", 24)] + [("tiles_" + k, 16) for k in BUILD_KINDS] + [("upgrade", 16), ("nuke", 16), ("warship", 8), ("myatt", 8), ("myboat", 8), ("myunit", 48), ("spawn", 64)]
OFF, o = {}, 0
for n, sz in DOM:
    OFF[n] = (o, sz); o += sz
NB = o                                      # 312
DOM_ID = np.concatenate([np.full(sz, i, np.int64) for i, (n, sz) in enumerate(DOM)])
N_PLAYERS, N_UNITS, N_ATT = 24, 48, 16
FP, FU, FA = 28, 20, 6
S_DIM = 48
G = 32                                      # grille geographique GxG, 4 canaux


def lg(x, s): return math.log1p(max(0.0, float(x))) / s


def player_feat(p, me_troops, max_rank_tiles):
    rel = [0.0] * 4; rel[int(p["relation"])] = 1.0 if isinstance(p["relation"], int) else 0.0
    if not isinstance(p["relation"], int): rel[{"Hostile": 0, "Distrustful": 1, "Neutral": 2, "Friendly": 3}.get(p["relation"], 2)] = 1.0
    ty = [0.0] * 3; ty[{"BOT": 0, "HUMAN": 1, "NATION": 2}.get(str(p["type"]).upper(), 0)] = 1.0
    f = [lg(p["tiles"], 12), lg(p["troops"], 14), min(4.0, p["troops"] / max(1.0, me_troops)) / 4.0, p["tiles"] / max(1, max_rank_tiles)] + rel + ty
    f += [float(p[k]) for k in ("allied", "traitor", "immune", "border", "canAttack", "canTrade", "embargoedByMe", "embargoesMe", "incomingRequest", "canAlly", "canDonateGold", "canDonateTroops", "canTarget", "canBreak", "canEmbargo", "canEmoji")]
    f += [1.0]
    return np.array(f + [0.0] * (FP - len(f)), np.float32)[:FP]


def build_obs(st, costs, cands, ctx):
    """st = state2 (dict), costs = {unit: gold}, cands = {'boat':[], 'tiles_<K>':[], 'upgrade':[], 'nuke':[], 'warship':[], 'spawn':[]}, ctx = {land_total, n_start, grid(np[4,G,G]), W, H, landmass_total}.
    Retourne dict de tableaux numpy + masques (type_mask [NT], ptr_mask [NT, NB])."""
    s = st["self"]; W, H = st["map"]["w"], st["map"]["h"]; mx = max(1, s["maxTroops"]); gold = s["gold"]; troops = s["troops"]
    w = st.get("win") or {}; land = max(1, w.get("landTiles") or ctx["land_total"]); thr = (w.get("thresholdTenths") or 800) / 1000.0     # VRAIE condition de victoire du moteur
    inc = sum(a["troops"] for a in st["incomingAttacks"] if not a["retreating"]); out_t = sum(a["troops"] for a in st["outgoingAttacks"])
    pl = st["players"][:N_PLAYERS]; max_rank = max([p["tiles"] for p in pl] + [s["tiles"], 1])
    u = s["units"]
    afford = [1.0 if gold >= costs.get(k, 1e18) else 0.0 for k in BUILD_KINDS + ["Warship"] + NUKE_T]
    sv = [lg(gold, 18), lg(troops, 15), troops / mx, s["tiles"] / land, min(1.5, s["tiles"] / (land * thr)), s["borderTiles"] / max(1, s["tiles"]), st["tick"] / 40000.0, float(s["immune"]), float(s["traitor"]), float(s["decaying"]),
          len(s["allies"]) / 4.0, s["tradingPartners"] / 8.0, s["boats"] / max(1, s["boatsMax"]), float(s["canEmbargoAll"]), lg(s["tradeGold"], 20), lg(s["trainGold"], 20), lg(s["piracyGold"], 20),
          inc / mx, out_t / mx, st["nOthersAlive"] / max(1, ctx["n_start"]), float(st["spawnPhase"]) if "spawnPhase" in st else 0.0]
    sv += [lg(u.get(k, 0), 4) for k in UNIT_T] + afford
    sv = np.array(sv + [0.0] * (S_DIM - len(sv)), np.float32)[:S_DIM]
    players = np.zeros((N_PLAYERS, FP), np.float32); pmask = np.zeros(N_PLAYERS, bool)
    for i, p in enumerate(pl): players[i] = player_feat(p, troops, max_rank); pmask[i] = True
    units = np.zeros((N_UNITS, FU), np.float32); umask = np.zeros(N_UNITS, bool); myu = st["units"][:N_UNITS]
    for i, x in enumerate(myu):
        oh = [0.0] * len(UNIT_T)
        if x["type"] in UNIT_T: oh[UNIT_T.index(x["type"])] = 1.0              # types transitoires (Shell, SAMMissile, MIRVWarhead) : vecteur nul, sans planter
        units[i, :len(UNIT_T) + 4] = oh + [x["level"] / 5.0, x["x"] / W, x["y"] / H, float(x["upgradable"])]; umask[i] = True
    atts = np.zeros((N_ATT, FA), np.float32); amask = np.zeros(N_ATT, bool)
    for i, a in enumerate(st["outgoingAttacks"][:8]): atts[i] = [1, a["troops"] / mx, float(a["retreating"]), float(a["target"] is not None), 0, 0]; amask[i] = True
    for i, a in enumerate(st["incomingAttacks"][:8]): atts[8 + i] = [0, a["troops"] / mx, float(a["retreating"]), 1, 0, 0]; amask[8 + i] = True
    bank = np.zeros((NB, FC), np.float32); bmask = np.zeros(NB, bool)

    def put(dom, i, vec):
        o, sz = OFF[dom]
        if i < sz: bank[o + i, :min(FC, len(vec))] = vec[:FC]; bmask[o + i] = True
    for i, p in enumerate(pl): put("players", i, players[i, :FC])
    for i, c in enumerate(cands.get("boat", [])[:24]):
        ot = [0.0] * 3
        if c["ownerType"]: ot[{"BOT": 0, "HUMAN": 1, "NATION": 2}.get(str(c["ownerType"]).upper(), 0)] = 1.0
        put("boat", i, np.array([c["x"] / W, c["y"] / H, c["landmassSize"] / land, float(c["owner"] is None), lg(c["ownerTiles"], 12), lg(c["ownerTroops"], 14), min(4.0, c["ownerTroops"] / max(1.0, troops)) / 4.0] + ot, np.float32))
    for k in BUILD_KINDS:
        for i, c in enumerate(cands.get("tiles_" + k, [])[:16]): put("tiles_" + k, i, np.array([c["x"], c["y"], float(c["shore"]), c["mag"], float(c["border"]), float(c["railOverlap"]), lg(c["cost"], 15)], np.float32))
    for i, c in enumerate(cands.get("upgrade", [])[:16]):
        oh = [0.0] * len(UPG_T)
        if c["type"] in UPG_T: oh[UPG_T.index(c["type"])] = 1.0
        put("upgrade", i, np.array(oh + [c["level"] / 5.0, c["x"] / W, c["y"] / H, lg(c["cost"][0] if c["cost"] else 1e12, 15), float(bool(c["cost"]) and gold >= c["cost"][0])], np.float32))
    for i, c in enumerate(cands.get("nuke", [])[:16]):
        put("nuke", i, np.array([c["x"], c["y"], lg(c["ownerTiles"], 12), lg(c["cost"], 18)], np.float32))
    for i, c in enumerate(cands.get("warship", [])[:8]): put("warship", i, np.array([c["x"], c["y"], lg(c["cost"], 15)], np.float32))
    for i, a in enumerate(st["outgoingAttacks"][:8]): put("myatt", i, np.array([a["troops"] / mx, float(a["retreating"])], np.float32))
    boats = [x for x in myu if x["type"] == "Transport"][:8]
    for i, b in enumerate(boats): put("myboat", i, np.array([b["x"] / W, b["y"] / H], np.float32))
    for i, x in enumerate(myu): put("myunit", i, units[i, :len(UNIT_T) + 4])
    for i, c in enumerate(cands.get("spawn", [])[:64]): put("spawn", i, np.array([c[0] / W, c[1] / H, c[2] / land], np.float32))
    # ---- masques de types et de pointeurs (exacts : fournis par le moteur) ----
    tm = np.zeros(NT, bool); pm = np.zeros((NT, NB), bool); spawn_phase = bool(st.get("spawnPhase", False))
    def ptr(t, dom, sel=None):
        o, sz = OFF[dom]; m = bmask[o:o + sz].copy()
        if sel is not None: m &= sel[:sz]
        pm[T[t], o:o + sz] = m; tm[T[t]] = bool(m.any())
    if spawn_phase:
        ptr("SPAWN", "spawn"); tm[T["STOP"]] = False
        return {"self": sv, "players": players, "pmask": pmask, "units": units, "umask": umask, "atts": atts, "amask": amask, "bank": bank, "bmask": bmask, "type_mask": tm, "ptr_mask": pm, "grid": ctx["grid"]}
    tm[T["STOP"]] = True
    P = lambda key: np.array([bool(p[key]) for p in pl] + [False] * (N_PLAYERS - len(pl)), bool)
    notal = np.array([not p["allied"] for p in pl] + [False] * (N_PLAYERS - len(pl)), bool)
    ok_troops = troops > 2000
    if ok_troops: tm[T["ATTACK_NEUTRAL"]] = True
    if ok_troops: ptr("ATTACK_PLAYER", "players", P("border") & P("canAttack") & notal)
    if ok_troops and s["boats"] < s["boatsMax"] and troops > 5000: ptr("BOAT", "boat")
    for k in BUILD_KINDS:
        if gold >= costs.get(k, 1e18): ptr("BUILD_" + k, "tiles_" + k)
    up = np.array([bool(c["cost"]) and gold >= c["cost"][0] for c in cands.get("upgrade", [])[:16]] + [False] * 16, bool)[:16]
    ptr("UPGRADE", "upgrade", up)
    for nk in NUKE_T:
        if u.get("Missile Silo", 0) > 0 and gold >= costs.get(nk, 1e18): ptr("NUKE_" + nk, "nuke")
    if u.get("Port", 0) > 0 and gold >= costs.get("Warship", 1e18): ptr("BUILD_Warship", "warship")
    if u.get("Warship", 0) > 0: ptr("MOVE_WARSHIPS", "warship")
    ptr("CANCEL_ATTACK", "myatt", np.array([not a["retreating"] for a in st["outgoingAttacks"][:8]] + [False] * 8, bool)[:8])
    ptr("CANCEL_BOAT", "myboat"); ptr("DELETE_UNIT", "myunit", np.array([x["type"] not in ("Transport", "Trade Ship", "Train") for x in myu] + [False] * N_UNITS, bool)[:N_UNITS])
    ptr("ALLY_REQUEST", "players", P("canAlly") | P("incomingRequest")); ptr("ALLY_REJECT", "players", P("incomingRequest"))
    ptr("ALLY_EXTEND", "players", P("allied")); ptr("ALLY_BREAK", "players", P("canBreak")); ptr("TARGET_PLAYER", "players", P("canTarget"))
    if gold > 0: ptr("DONATE_GOLD", "players", P("canDonateGold"))
    if troops > 0: ptr("DONATE_TROOPS", "players", P("canDonateTroops"))
    ptr("EMOJI", "players", P("canEmoji"))
    ptr("EMBARGO_ON", "players", P("canEmbargo") & ~P("embargoedByMe")); ptr("EMBARGO_OFF", "players", P("embargoedByMe"))
    if s["canEmbargoAll"]: tm[T["EMBARGO_ALL_ON"]] = True; tm[T["EMBARGO_ALL_OFF"]] = True
    return {"self": sv, "players": players, "pmask": pmask, "units": units, "umask": umask, "atts": atts, "amask": amask, "bank": bank, "bmask": bmask, "type_mask": tm, "ptr_mask": pm, "grid": ctx["grid"]}


def decode(t, ptr_idx, param, st, cands, me_units):
    """(type, indice dans la banque, parametre) -> intent moteur (sans clientID) ou None."""
    name = TYPES[t]; s = st["self"]; fr = float(FRACS[param]) if param is not None else 0.0
    def at(dom): return ptr_idx - OFF[dom][0]
    if name == "STOP": return None
    if name == "SPAWN": c = cands["spawn"][at("spawn")]; return {"type": "spawn", "tile": c[3]}
    if name == "ATTACK_NEUTRAL": return {"type": "attack", "targetID": None, "troops": int(s["troops"] * fr)}
    if name == "ATTACK_PLAYER": return {"type": "attack", "targetID": st["players"][at("players")]["id"], "troops": int(s["troops"] * fr)}
    if name == "BOAT": return {"type": "boat", "dst": cands["boat"][at("boat")]["tile"], "troops": int(s["troops"] * fr)}
    if name.startswith("BUILD_") and name != "BUILD_Warship": k = name[6:]; return {"type": "build_unit", "unit": k, "tile": cands["tiles_" + k][at("tiles_" + k)]["tile"]}
    if name == "BUILD_Warship": return {"type": "build_unit", "unit": "Warship", "tile": cands["warship"][at("warship")]["tile"]}
    if name == "UPGRADE": c = cands["upgrade"][at("upgrade")]; return {"type": "upgrade_structure", "unit": c["type"], "unitId": c["id"], "amount": 1}
    if name.startswith("NUKE_"): return {"type": "build_unit", "unit": name[5:], "tile": cands["nuke"][at("nuke")]["tile"]}
    if name == "MOVE_WARSHIPS": return {"type": "move_warship", "unitIds": [x["id"] for x in me_units if x["type"] == "Warship"], "tile": cands["warship"][at("warship")]["tile"]}
    if name == "CANCEL_ATTACK": return {"type": "cancel_attack", "attackID": st["outgoingAttacks"][at("myatt")]["id"]}
    if name == "CANCEL_BOAT": return {"type": "cancel_boat", "unitID": [x for x in me_units if x["type"] == "Transport"][at("myboat")]["id"]}
    if name == "DELETE_UNIT": return {"type": "delete_unit", "unitId": me_units[at("myunit")]["id"]}
    pid = lambda: st["players"][at("players")]["id"]
    if name == "ALLY_REQUEST": return {"type": "allianceRequest", "recipient": pid()}
    if name == "ALLY_REJECT": return {"type": "allianceReject", "requestor": pid()}
    if name == "ALLY_EXTEND": return {"type": "allianceExtension", "recipient": pid()}
    if name == "ALLY_BREAK": return {"type": "breakAlliance", "recipient": pid()}
    if name == "TARGET_PLAYER": return {"type": "targetPlayer", "target": pid()}
    if name == "DONATE_GOLD": return {"type": "donate_gold", "recipient": pid(), "gold": int(s["gold"] * fr)}
    if name == "DONATE_TROOPS": return {"type": "donate_troops", "recipient": pid(), "troops": int(s["troops"] * fr)}
    if name == "EMBARGO_ON": return {"type": "embargo", "targetID": pid(), "action": "start"}
    if name == "EMBARGO_OFF": return {"type": "embargo", "targetID": pid(), "action": "stop"}
    if name == "EMOJI": return {"type": "emoji", "recipient": pid(), "emoji": EMOJI_IDX[param if param is not None else 0]}
    if name == "EMBARGO_ALL_ON": return {"type": "embargo_all", "action": "start"}
    if name == "EMBARGO_ALL_OFF": return {"type": "embargo_all", "action": "stop"}
    return None
