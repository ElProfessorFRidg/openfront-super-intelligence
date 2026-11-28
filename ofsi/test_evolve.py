"""Test de la logique de selection de l'evolution v2 (evaluations factices a verite connue) : confirmation en deux temps, egalite -> parent, reprise."""
import os, sys, json, tempfile, pathlib, argparse, importlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
T = tempfile.mkdtemp(); os.environ["OFSI_EVOLVE"] = T
import ofsi.rl2.evolve as E; importlib.reload(E)
ok = []
def check(n, c): ok.append(bool(c)); print(("PASS " if c else "FAIL ") + n)
def fake(wins_by_call):
    calls = {"n": 0}
    def ev(cands, specs, workers):
        w = wins_by_call[min(calls["n"], len(wins_by_call) - 1)]; calls["n"] += 1
        return {i: [{"win": k < w[i], "progress": 0.5, "end": "x"} for k in range(len(specs))] for i in range(len(cands))}
    return ev, calls
def run(wins, confirm=True, gens=1):
    for f in pathlib.Path(T).glob("*"): f.unlink()
    E.evaluate, calls = fake(wins)[0], None
    a = argparse.Namespace(gens=gens, lam=2, workers=1, seed=0, per=1, seed0=1, confirm=confirm, confirm_seed0=9)
    parent = E.search(a); return parent, [json.loads(l) for l in open(pathlib.Path(T) / "gens.jsonl")]
# gen: parent 5 victoires, enfants 5 et 9 (meilleur = enfant 2) ; confirmation (appel suivant) : parent 5, enfant 8 -> remplace
p, h = run([[5, 5, 9], [5, 8]]); check("enfant meilleur ET confirme : remplace le parent", h[0]["replaced"] and h[0]["confirmation"] == {"parent": 5, "enfant": 8} and p != E.BASE)
# confirmation echoue (enfant 4 < parent 5) -> parent conserve
p, h = run([[5, 5, 9], [5, 4]]); check("enfant meilleur en generation mais PIRE en confirmation : parent conserve", (not h[0]["replaced"]) and p == E.BASE)
# egalite en confirmation (5 = 5) -> parent conserve (strictement plus de victoires exige)
p, h = run([[5, 5, 9], [5, 5]]); check("egalite en confirmation : parent conserve", (not h[0]["replaced"]) and p == E.BASE)
# aucun enfant meilleur -> pas de confirmation du tout
p, h = run([[9, 5, 5]]); check("aucun enfant meilleur : pas de confirmation, parent conserve", h[0]["confirmation"] is None and not h[0]["replaced"])
# sans --confirm (comportement v1) : l'enfant meilleur remplace directement
p, h = run([[5, 5, 9]], confirm=False); check("sans confirmation (v1) : remplacement direct", h[0]["replaced"] and h[0]["confirmation"] is None)
print(f"{sum(ok)}/{len(ok)} PASS"); sys.exit(0 if all(ok) else 1)
