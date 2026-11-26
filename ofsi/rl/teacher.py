"""Professeur dans l'espace d'actions de la politique (heuristique prudente 'conqueror_v1'). Sert a l'amorcage par imitation, jamais de plafond."""
import numpy as np
from ofsi.rl import spec

def teacher_action(obs, nb, mask, ratio=1.6, send=3, expand=2):
    """Retourne (type, frac_index). send/expand = indices dans spec.FRACS (3->0.5, 2->0.3)."""
    s = obs["self"]; troops = s["troops"]
    if mask[spec.T_BUILD] and s["units"].get("City", 0) < 2 + s["tiles"] // 500: return spec.T_BUILD, 0
    cand = [(o["troops"], k) for k, o in enumerate(nb) if not o["allied"]]
    if cand:
        t, k = min(cand)
        if troops > ratio * t and mask[spec.T_ATTACK + k]: return spec.T_ATTACK + k, send
    if troops > 3000 and mask[spec.T_EXPAND]: return spec.T_EXPAND, expand
    return spec.T_NOOP, 0
