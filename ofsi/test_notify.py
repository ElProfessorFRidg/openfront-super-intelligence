"""Tests des notifications et de la banniere (donnees synthetiques dans un dossier temporaire ; ne touche jamais aux vrais runs)."""
import os, sys, json, tempfile, pathlib, time, importlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
tmp = pathlib.Path(tempfile.mkdtemp()); os.environ["OFSI_RUNS"] = str(tmp / "runs"); os.environ["OFSI_VALIDATION"] = str(tmp / "validation.json")
import ofsi.notify as N; importlib.reload(N)
ok = []
def check(name, cond): ok.append(bool(cond)); print(("PASS " if cond else "FAIL ") + name)
def mk(run, rows):
    d = N.RUNS / run; d.mkdir(parents=True, exist_ok=True); (d / "metrics.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
def row(u, wr, dps=20.0, steps=None): return {"update": u, "env_steps": steps if steps is not None else u * 400, "decisions_per_s": dps, "recent200_winrate": wr, "pg_loss": 0.0, "v_loss": 0.1}

# 1. deduplication : meme cle -> une seule notification
check("notify ajoute", N.notify("k1", "t", "d", "info")); check("notify deduplique", not N.notify("k1", "t", "d", "info")); check("lecture", len(N.read()) == 1)
# 2. plateau
mk("plat", [row(u, 0.50 + (0.005 if u % 2 else 0), steps=30000 + u) for u in range(1, 61)]); new = N.scan(); check("plateau detecte", any(k.startswith("plateau:plat") for k in new))
check("plateau pas re-notifie", not any(k.startswith("plateau:plat") for k in N.scan()))
# 3. pas de plateau si le taux progresse
mk("prog", [row(u, u / 100, steps=30000 + u) for u in range(1, 61)]); check("pas de plateau si progression", not any(k.startswith("plateau:prog") for k in N.scan()))
# 4. regression
mk("reg", [row(u, 0.8) for u in range(1, 16)] + [row(u, 0.4) for u in range(16, 22)]); check("regression detectee", any(k.startswith("regress:reg") for k in N.scan()))
# 5. record de debit
mk("rec", [row(u, 0.5, dps=10.0) for u in range(1, 12)] + [row(12, 0.5, dps=40.0)]); check("record de debit detecte", any(k.startswith("record:rec") for k in N.scan()))
# 6. divergence
mk("nan", [row(1, 0.5), dict(row(2, 0.5), pg_loss=float("nan"))]); check("divergence detectee", any(k == "nan:nan" for k in N.scan()))
# 7. banniere : jamais 'validee' sans validation.json explicite
st = N.status(); check("banniere sans validation = partielle ou en cours", "VALIDÉE" not in st["banner"])
(tmp / "validation.json").write_text(json.dumps({"all_pass": False})); check("all_pass=false -> pas validee", "VALIDÉE" not in N.status()["banner"])
(tmp / "validation.json").write_text("pas du json"); check("fichier corrompu -> pas validee", "VALIDÉE" not in N.status()["banner"])
(tmp / "validation.json").write_text(json.dumps({"all_pass": True})); check("all_pass=true -> validee", "VALIDÉE" in N.status()["banner"])
# 8. 'en cours' quand les metriques sont recentes
os.remove(tmp / "validation.json"); check("run recent -> ENTRAINEMENT EN COURS", N.status()["banner"] == "ENTRAÎNEMENT EN COURS")
old = time.time() - 3600
for f in N.RUNS.glob("*/metrics.jsonl"): os.utime(f, (old, old))
check("runs anciens -> VALIDATION PARTIELLE", N.status()["banner"].startswith("VALIDATION PARTIELLE"))
print(f"{sum(ok)}/{len(ok)} PASS"); sys.exit(0 if all(ok) else 1)
