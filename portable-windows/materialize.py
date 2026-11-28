"""Rend les dépendances npm transportables après extraction du ZIP."""
import json
import os
from pathlib import Path
import shutil
import sys


def forward_workspace(entry, target):
    # TSX resolves tsconfig aliases from the original source tree. A full
    # copy in node_modules would bypass that resolution for workspace imports.
    metadata = json.loads((target / "package.json").read_text(encoding="utf-8"))
    metadata["exports"] = {key: value.removesuffix(".ts") + ".mjs"
                           for key, value in metadata["exports"].items()}
    source = target / "src"
    for file in source.rglob("*.ts"):
        if file.name.endswith(".d.ts"):
            continue
        shim = entry / "src" / file.relative_to(source).with_suffix(".mjs")
        shim.parent.mkdir(parents=True, exist_ok=True)
        relative = Path(os.path.relpath(file, shim.parent)).as_posix()
        shim.write_text(f"export * from {json.dumps(relative)};\n", encoding="utf-8")
    (entry / "package.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")


def main(engine):
    modules = engine / "node_modules"
    for root, directories, files in os.walk(modules):
        for name in directories + files:
            entry = Path(root) / name
            junction = getattr(entry, "is_junction", lambda: False)()
            if not entry.is_symlink() and not junction:
                continue
            target = entry.resolve(strict=True)
            if not target.is_relative_to(engine):
                raise RuntimeError(f"Lien externe : {entry} → {target}")
            if junction:
                entry.rmdir()
            else:
                entry.unlink()
            if entry.parent == modules / "@openfront" and target.parent == engine / "packages":
                forward_workspace(entry, target)
            elif target.is_dir():
                shutil.copytree(target, entry)
            else:
                shutil.copy2(target, entry)


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
