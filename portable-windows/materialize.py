"""Remplace les jonctions absolues npm Workspaces par des répertoires transportables."""
import os
from pathlib import Path
import shutil
import sys


def main(engine):
    modules = engine / "node_modules"
    for root, directories, files in os.walk(modules):
        for name in directories + files:
            entry = Path(root) / name
            if not entry.is_symlink() and not entry.is_junction():
                continue
            target = entry.resolve(strict=True)
            if not target.is_relative_to(engine):
                raise RuntimeError(f"Lien externe : {entry} → {target}")
            if entry.is_junction():
                entry.rmdir()
            else:
                entry.unlink()
            if target.is_dir():
                shutil.copytree(target, entry)
            else:
                shutil.copy2(target, entry)


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
