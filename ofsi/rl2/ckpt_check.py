"""Verification de portabilite d'un checkpoint (cloud <-> PC) : integrite SHA-256, chargement sur CPU, correspondance des cles avec PolicyV2, finitude, presence de l'etat de reprise.
Usage : python ofsi/rl2/ckpt_check.py runs/arm_C_medium/ckpt_latest.pt [...]"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import torch
from ofsi.rl2 import ckpt
from ofsi.rl2.model import PolicyV2


def check(path):
    out = {"fichier": path, "ok": True, "problemes": []}
    def bad(m): out["ok"] = False; out["problemes"].append(m)
    try: c = ckpt.load(path, "cpu")
    except Exception as e: bad(f"chargement/SHA : {e}"); return out
    sd = c["model"]
    try: m = ckpt.build_model(c, "cpu"); out["architecture"] = c.get("arch") or "deduite des formes : " + str(ckpt.arch_from_state(sd))
    except Exception as e: bad(f"architecture/chargement : {e}"); return out
    ref = m.state_dict()
    if set(sd) != set(ref): bad(f"cles differentes : manquantes {sorted(set(ref) - set(sd))[:3]} en trop {sorted(set(sd) - set(ref))[:3]}")
    else:
        for k, v in sd.items():
            if v.shape != ref[k].shape: bad(f"forme {k}: {tuple(v.shape)} != {tuple(ref[k].shape)}"); break
            if not torch.isfinite(v.float()).all(): bad(f"valeurs non finies dans {k}"); break
    out["etat_de_reprise"] = {k: (k in c) for k in ("opt", "update", "env_steps", "stage", "cur_log", "t_total")}
    out["reprenable"] = all(out["etat_de_reprise"].values()); out["meta"] = c.get("meta", "absente (checkpoint anterieur a la tracabilite)")
    out["tenseurs_sur_cuda"] = any(getattr(v, "is_cuda", False) for v in sd.values()); out["update"] = c.get("update")
    return out


if __name__ == "__main__":
    import json
    for p in sys.argv[1:]: r = check(p); print(json.dumps(r, ensure_ascii=False))
