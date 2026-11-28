"""Tests de l'orchestrateur : promotion (candidat significativement meilleur), non-promotion (difference non significative / pire), reprise (aucun recalcul). Evaluations factices a verite connue."""
import os, sys, json, tempfile, pathlib, importlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
T = pathlib.Path(tempfile.mkdtemp()); os.environ["OFSI_ORCH"] = str(T / "orch"); os.environ["OFSI_RUNS"] = str(T / "runs")
import ofsi.orchestrator as O; importlib.reload(O)
ok = []
def check(n, c): ok.append(bool(c)); print(("PASS " if c else "FAIL ") + n)
def fake_eval(path, wins):
    pathlib.Path(path).write_text(json.dumps({"parties": [{"cfg": {"_id": i}, "win": bool(w)} for i, w in enumerate(wins)]}))
champ = T / "champ.pt"; champ.write_bytes(b"champion-v0"); calls = {"train": 0, "eval": 0}; CREATED = set()      # dossiers crees PAR CE TEST : seuls ceux-la seront supprimes (JAMAIS un glob sur runs/ : defaut corrige le 2026-11-29)
def make(cand_wins, champ_wins):
    def fake_run(cmd, logf):
        calls["train"] += 1; name = cmd[cmd.index("--name") + 1]; d = O.ROOT / "runs" / name; assert not d.exists() or name in CREATED, f"le test refuse d'ecraser un vrai dossier {d}"; CREATED.add(name); d.mkdir(parents=True, exist_ok=True); (d / "ckpt_latest.pt").write_bytes(("cand-" + name).encode()); (d / "metrics.jsonl").write_text("{}\n"); return 0
    def fake_evaluate(ckpt, a, tag):
        calls["eval"] += 1; out = O.ORCH / f"eval_{O.sha8(ckpt)}_{tag}.json"; O.ORCH.mkdir(parents=True, exist_ok=True)
        if not out.exists(): fake_eval(out, champ_wins if str(ckpt) == str(champ) or "champ" in str(ckpt) else cand_wins)
        return out
    return fake_run, fake_evaluate
def go(cand_wins, champ_wins, extra=()):
    O.run, O.evaluate = make(cand_wins, champ_wins); sys.argv = ["orch", "--init", str(champ), "--cycles", "1", "--budget", "1"] + list(extra); O.main()
    return json.loads(O.CHAMP.read_text()), [e for e in (json.loads(l) for l in open(O.CYCLES)) if e.get("event") == "cycle"]
# 1. candidat net : 12 victoires de plus sur 12 parties, 0 inverse -> p = 2/2^12 << 0,05 -> promu
ch, cy = go([1] * 12, [0] * 12); check("candidat significativement meilleur : promu", cy[-1]["promu"] and ch["ckpt"] != str(champ) and len(ch["history"]) == 2)
import shutil; shutil.rmtree(T / "orch"); [shutil.rmtree(O.ROOT / "runs" / n, ignore_errors=True) for n in list(CREATED)]
# 2. difference non significative (5 gagnees / 3 perdues, p=0,73) -> non promu
ch, cy = go([1] * 5 + [0] * 3 + [1] * 4, [0] * 5 + [1] * 3 + [1] * 4); check("difference non significative : NON promu, champion inchange", (not cy[-1]["promu"]) and ch["ckpt"] == str(champ))
shutil.rmtree(T / "orch"); [shutil.rmtree(O.ROOT / "runs" / n, ignore_errors=True) for n in list(CREATED)]
# 3. candidat pire -> non promu
ch, cy = go([0] * 12, [1] * 12); check("candidat significativement PIRE : non promu", not cy[-1]["promu"] and ch["ckpt"] == str(champ))
shutil.rmtree(T / "orch"); [shutil.rmtree(O.ROOT / "runs" / n, ignore_errors=True) for n in list(CREATED)]
# 4. reprise : un 2e lancement n'entraine ni n'evalue de nouveau
ch, cy = go([1] * 12, [0] * 12); t0, e0 = calls["train"], calls["eval"]
O.run, O.evaluate = make([1] * 12, [0] * 12); sys.argv = ["orch", "--cycles", "1", "--budget", "1"]; O.main()
check("reprise : champion lu depuis l'etat, cycle suivant demarre depuis le NOUVEAU champion", json.loads(O.CHAMP.read_text())["ckpt"] != str(champ))
# 5. arret propre
(O.ORCH / "STOP").write_text("1"); n = calls["train"]; sys.argv = ["orch", "--cycles", "3", "--budget", "1"]; O.main(); check("STOP : aucun entrainement lance", calls["train"] == n)
shutil.rmtree(O.ROOT / "runs", ignore_errors=True) if False else None
for n in CREATED: shutil.rmtree(O.ROOT / "runs" / n, ignore_errors=True)
print(f"{sum(ok)}/{len(ok)} PASS"); sys.exit(0 if all(ok) else 1)
