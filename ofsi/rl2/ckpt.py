"""Checkpoints atomiques + somme de controle SHA-256 (ecriture dans un fichier temporaire puis remplacement) et rotation des anciennes copies valides."""
import os, hashlib, glob
import torch


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def save(path, payload, keep=3):
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
