"""Checkpoints atomiques + somme de controle SHA-256 (ecriture dans un fichier temporaire puis remplacement) et rotation des anciennes copies valides."""
import os, hashlib, glob
import torch


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


DEFAULT_ARCH = {"d": 128, "layers": 4, "heads": 4, "ff": 512}


def arch_from_state(sd, heads=None):
    """Architecture deduite des FORMES du state_dict (checkpoints anterieurs a `arch`). `heads` n'est pas deductible des formes : defaut 4 (valeur de tous les anciens checkpoints)."""
    d = sd["e_self.0.weight"].shape[0]; layers = 1 + max(int(k.split(".")[2]) for k in sd if k.startswith("enc.layers.")); ff = sd["enc.layers.0.linear1.weight"].shape[0]
    return {"d": int(d), "layers": int(layers), "heads": int(heads or DEFAULT_ARCH["heads"]), "ff": int(ff)}


def build_model(payload, device="cpu"):
    """Construit PolicyV2 avec l'architecture DU CHECKPOINT (champ `arch`, sinon deduite des formes) puis charge les poids. Unique point d'entree pour charger un reseau."""
    from ofsi.rl2.model import PolicyV2
    arch = payload.get("arch") or arch_from_state(payload["model"]); m = PolicyV2(**arch).to(device); m.load_state_dict(payload["model"]); return m


def meta():
    """Provenance du checkpoint (portabilite cloud <-> PC : savoir ou, avec quoi et quand il a ete produit)."""
    import platform, time, subprocess
    try: commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception: commit = ""
    return {"torch": torch.__version__, "cuda": bool(torch.cuda.is_available()), "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu", "platform": platform.platform()[:60], "cpus": __import__("os").cpu_count(), "git": commit, "saved": time.strftime("%Y-%m-%d %H:%M:%S")}


def save(path, payload, keep=3):
    payload = {**payload, "meta": meta()} if "meta" not in payload else payload
    if "model" in payload and "arch" not in payload: payload = {**payload, "arch": arch_from_state(payload["model"])}
    tmp = path + ".tmp"
    torch.save(payload, tmp)
    digest = sha(tmp)
    os.replace(tmp, path)
    with open(path + ".sha256", "w") as f:
        f.write(digest)
    if keep and "update" in payload:                        # copie datee pour retour arriere
        snap = path.replace("_latest.pt", f"_u{payload['update']:06d}.pt")
        if snap != path:
            torch.save(payload, snap)
            with open(snap + ".sha256", "w") as f:
                f.write(sha(snap))
            old = sorted(glob.glob(path.replace("_latest.pt", "_u*.pt")))
            for p in old[:-keep]:
                for q in (p, p + ".sha256"):
                    if os.path.exists(q):
                        os.remove(q)


def load(path, map_location="cpu"):
    if not os.path.exists(path + ".sha256"):
        raise RuntimeError(f"somme de controle absente pour {path}")
    if open(path + ".sha256").read().strip() != sha(path):
        raise RuntimeError(f"checkpoint corrompu (SHA-256 different) : {path}")
    return torch.load(path, map_location=map_location, weights_only=False)
