"""Checkpoints atomiques + somme de controle SHA-256 (ecriture dans un fichier temporaire puis remplacement) et rotation des anciennes copies valides."""
import os, hashlib, glob
import torch


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def meta():
    """Provenance du checkpoint (portabilite cloud <-> PC : savoir ou, avec quoi et quand il a ete produit)."""
    import platform, time, subprocess
    try: commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception: commit = ""
    return {"torch": torch.__version__, "cuda": bool(torch.cuda.is_available()), "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu", "platform": platform.platform()[:60], "cpus": __import__("os").cpu_count(), "git": commit, "saved": time.strftime("%Y-%m-%d %H:%M:%S")}


def save(path, payload, keep=3):
    payload = {**payload, "meta": meta()} if "meta" not in payload else payload
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
