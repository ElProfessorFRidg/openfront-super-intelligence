"""Audit AUTOMATIQUE du moteur officiel epingle : graphe de creation des executions, predicats de legalite du joueur, effets de bord.
Sortie : registry/engine_audit.json. Aucune connaissance saisie a la main sur les mecaniques : tout vient de l'analyse du code."""
import re, json, pathlib, subprocess
ROOT = pathlib.Path(__file__).resolve().parents[1]; E = ROOT / "vendor/openfront-engine/packages/engine/src"
files = {p.stem: p for p in E.rglob("*.ts")}
exec_names = sorted(n for n in files if n.endswith("Execution") and (E / "execution" / (n + ".ts")).exists())
creators = {n: set() for n in exec_names}
for path in E.rglob("*.ts"):
    txt = path.read_text(encoding="utf-8", errors="ignore")
    for m in re.finditer(r"new\s+([A-Za-z]+Execution)\s*\(", txt):
        if m.group(1) in creators and path.stem != m.group(1): creators[m.group(1)].add(path.stem)
# classification : creee par l'Executor (intent) / par une autre execution / par le moteur (init)
cls = {}
for n, c in creators.items():
    kind = "intent" if "ExecutionManager" in c else ("emergent" if c else "interne/aucune creation detectee")
    cls[n] = {"created_by": sorted(c), "kind": kind}
# intents du dispatcher -> execution
em = (E / "execution/ExecutionManager.ts").read_text(encoding="utf-8")
disp = {}
for m in re.finditer(r'case "([a-zA-Z_]+)":\s*(?:\{\s*)?return new ([A-Za-z]+Execution)', em): disp[m.group(1)] = m.group(2)
# predicats de legalite exposes par Player
game = (E / "game/Game.ts").read_text(encoding="utf-8")
pl = game[game.index("export interface Player "):]; pl = pl[:pl.index("\n}\n")]
preds = sorted(set(re.findall(r"\n\s+((?:can|has|is)[A-Za-z]*)\(", pl)))
# constantes de regles utiles
cfg = (ROOT / "vendor/openfront-engine/packages/engine-lib/src/configuration/Config.ts").read_text(encoding="utf-8")
consts = {k: v for k, v in re.findall(r"\nconst ([A-Z_]+) = ([0-9_.*\s+\-/()A-Za-z]+);", cfg)}
rules = sorted(set(re.findall(r"\n  ((?:[a-z][A-Za-z]*)(?:Max|Number|Range|Cooldown|Duration|Cost|Gold|Rate|Limit|Radius|Threshold)[A-Za-z]*)\(", cfg)))
commit = subprocess.run(["git", "-C", str(ROOT / "vendor/openfront-engine"), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
out = {"engine_commit": commit, "executions": cls, "intent_dispatch": disp, "player_predicates": preds, "rule_constants": consts, "rule_functions": rules}
(ROOT / "registry/engine_audit.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
by = {}
for n, c in cls.items(): by.setdefault(c["kind"], []).append(n)
print("executions:", len(cls)); [print(" ", k, len(v), v) for k, v in by.items()]
print("dispatch intents->exec:", len(disp)); print("predicats joueur:", len(preds), preds); print("fonctions de regle (cout/portee/duree...):", len(rules))
