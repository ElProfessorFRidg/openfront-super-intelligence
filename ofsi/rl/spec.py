"""Espace d'observation/d'action v1 (sous-ensemble 'macro' des mécaniques; voir registry/coverage.md pour ce qui est couvert)."""
import math
import numpy as np

K = 6                                  # emplacements de voisins
FRACS = np.array([0.05, 0.15, 0.30, 0.50, 0.80], dtype=np.float32)
BUILD_UNITS = ["City", "Port", "Defense Post", "Factory", "SAM Launcher", "Warship"]
UNIT_TYPES = ["Transport", "Warship", "Port", "Atom Bomb", "Hydrogen Bomb", "Trade Ship", "Missile Silo", "Defense Post", "SAM Launcher", "City", "MIRV", "Train", "Factory"]
# types d'action : 0 noop | 1 expand | 2..7 attack voisin k | 8..13 build | 14..19 alliance voisin k
N_TYPES = 2 + K + len(BUILD_UNITS) + K
T_NOOP, T_EXPAND, T_ATTACK, T_BUILD, T_ALLY = 0, 1, 2, 2 + K, 2 + K + len(BUILD_UNITS)
USES_FRAC = np.zeros(N_TYPES, dtype=bool); USES_FRAC[1:2 + K] = True
REL = {"Hostile": 0, "Distrustful": 1, "Neutral": 2, "Friendly": 3}
PT = {"Bot": 0, "Human": 1, "Nation": 2}
NB_F = 14
SELF_F = 7 + len(UNIT_TYPES) + len(BUILD_UNITS) + 3
OBS_DIM = SELF_F + K * NB_F

def _l(x, s): return math.log1p(max(0.0, x)) / s

def neighbors(obs):
    nb = [o for o in obs["others"] if o["border"]]
    nb.sort(key=lambda o: -o["tiles"]); return nb[:K]

def featurize(obs, n_start_players=1):
    """obs (dict du démon, avec costs/landTotal) -> (vecteur float32, masque bool[N_TYPES], voisins)"""
    s = obs["self"]; costs = obs.get("costs") or {}; land = max(1, obs.get("landTotal") or 1)
    alive = 1 + len(obs["others"]); tiles = s["tiles"]
    f = [_l(s["gold"], 16), _l(s["troops"], 14), tiles / land, s["borderTiles"] / (tiles + 1), obs["tick"] / 20000.0, len(s["allies"]) / 4.0, alive / max(1, n_start_players)]
    f += [_l(s["units"].get(u, 0), 4) for u in UNIT_TYPES]
    f += [1.0 if s["gold"] >= costs.get(u, 1e18) else 0.0 for u in BUILD_UNITS]
    larger = sum(1 for o in obs["others"] if o["tiles"] > tiles)
    f += [larger / max(1, alive), _l(s["tradeGold"], 16), _l(s["goldEarned"], 18)]
    nb = neighbors(obs); mask = np.zeros(N_TYPES, dtype=bool); mask[T_NOOP] = True
    mine = max(1.0, s["troops"])
    for k in range(K):
        if k < len(nb):
            o = nb[k]; rel = [0.0] * 4; rel[REL.get(o["relation"], 2)] = 1.0; pt = [0.0] * 3; pt[PT.get(o["type"], 0)] = 1.0
            f += [1.0, _l(o["tiles"], 12), _l(o["troops"], 14), min(3.0, o["troops"] / mine) / 3.0] + rel + [1.0 if o["allied"] else 0.0, 1.0 if o["traitor"] else 0.0] + pt[:2] + [1.0 if o["canAlly"] else 0.0]
            f += [1.0 if o["incoming"] else 0.0]
            mask[T_ATTACK + k] = not o["allied"]
            mask[T_ALLY + k] = bool(o["canAlly"] or o["incoming"])
        else:
            f += [0.0] * NB_F
    mask[T_EXPAND] = s["troops"] > 2000
    for j, u in enumerate(BUILD_UNITS): mask[T_BUILD + j] = s["gold"] >= costs.get(u, 1e18)
    v = np.asarray(f, dtype=np.float32)
    assert v.shape[0] == OBS_DIM, (v.shape, OBS_DIM)
    return v, mask, nb

def share(obs):
    return obs["self"]["tiles"] / max(1, obs.get("landTotal") or 1)


def decode_intent(obs, cid, env, a_type, frac_i, nb, agent=0):
    """(type, fraction) -> intent moteur, ou None. Retourne (intent, build_failed)."""
    troops = int(obs["self"]["troops"] * FRACS[frac_i])
    if a_type == T_NOOP: return None, False
    if a_type == T_EXPAND: return {"type": "attack", "targetID": None, "troops": troops, "clientID": cid}, False
    if T_ATTACK <= a_type < T_ATTACK + K:
        k = a_type - T_ATTACK
        return ({"type": "attack", "targetID": nb[k]["id"], "troops": troops, "clientID": cid}, False) if k < len(nb) else (None, False)
    if T_BUILD <= a_type < T_ALLY:
        unit = BUILD_UNITS[a_type - T_BUILD]; tiles = env.build_tiles(unit, agent=agent)
        if not tiles: return None, True            # pas de tuile legale selon le moteur (mesure)
        return {"type": "build_unit", "unit": unit, "tile": tiles[0], "clientID": cid}, False
    if a_type >= T_ALLY:
        k = a_type - T_ALLY
        return ({"type": "allianceRequest", "recipient": nb[k]["id"], "clientID": cid}, False) if k < len(nb) else (None, False)
    return None, False
