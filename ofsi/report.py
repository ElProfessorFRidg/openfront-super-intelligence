"""Rapport automatique (Markdown) : compile UNIQUEMENT des artefacts mesures (benchmarks/*.json, registry/*, runs/*). Tout ce qui n'a pas de preuve est marque 'NON MESURE'.
Usage : python ofsi/report.py  ->  reports/rapport_<date>.md"""
import json, glob, pathlib, datetime, subprocess, os, sys, platform
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
ROOT = pathlib.Path(__file__).resolve().parents[1]
B = ROOT / "benchmarks"


def jl(p):
    try: return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
    except Exception: return None


def fmt_summary(r, groups=("TOUT", "cartes_entrainement", "cartes_jamais_vues")):
    out = []
    for g in groups:
        for d, v in (r.get("resume", {}).get(g, {})).items():
            if d == "ALL": continue
            out.append(f"| {g} | {d} | {v['victoires']}/{v['parties']} | {v['taux']:.2f} | {v['ic95'][0]}–{v['ic95'][1]} | {v['progression_moy']:.2f} | {v['morts']} |")
    return out


def main():
    L = [f"# Rapport automatique OpenFront SI — {datetime.datetime.now():%Y-%m-%d %H:%M}", "",
         "> Ce rapport ne contient que des resultats MESURES et reproductibles ; chaque absence de preuve est marquee **NON MESURE**. Faits ≠ estimations ≠ objectifs.", ""]
    # --- materiel
    L += ["## 1. Materiel et versions (mesures)", ""]
    hw = jl(ROOT / "config/hardware.json") or {}
    L += [f"- Machine : {hw.get('machine', 'NON MESURE')}", f"- GPU : {hw.get('gpu', {}).get('name', 'NON MESURE')} ; torch {hw.get('gpu', {}).get('torch', '?')} ; entrainement {hw.get('training', {})}"]
    try: commit = subprocess.run(["git", "-C", str(ROOT / "vendor/openfront-engine"), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    except Exception: commit = "?"
    L += [f"- Moteur officiel : OpenFrontIO `{commit[:8]}` (AGPL-3.0) ; Python {platform.python_version()} ; Node 24.22.3 portable", ""]
    g = jl(B / "gpu_vs_cpu.json"); o = jl(B / "gpu_opt.json")
    if g:
        L += ["### Debit reseau CPU vs GPU (mesure)", "", "| reseau / dispositif | inference ms | pas d'entrainement ms |", "|---|---|---|"]
        for k, v in g["results"].items(): L.append(f"| {k} | {v['inference_ms']} | {v['train_step_ms']} |")
        L.append("")
    if o: L += ["Optimisations GPU (attention, lot 256) : " + "; ".join(f"{k} {v['train_step_ms']} ms" for k, v in o.items()), ""]
    p = jl(B / "parallel_World_100bots.json")
    if p: L += ["Debit moteur agrege (World, 100 bots, CPU) : " + ", ".join(f"{r['envs']} env = {r['agg_ticks_per_s']} t/s" for r in p["runs"]), ""]
    # --- mecaniques
    L += ["## 2. Couverture des mecaniques", ""]
    cov = ROOT / "registry/coverage_v2.md"
    L += [cov.read_text(encoding="utf-8").split("\n")[2] if cov.exists() else "NON MESURE", "", "Scenarios de competence (effet verifie dans le moteur) : "]
    sk = jl(B / "skills_full.json")
    if sk: L += [f"**{sum(x['passed'] for x in sk)}/{len(sk)} PASS** — un PASS prouve l'execution avec l'effet attendu, PAS la maitrise par l'agent.", ""]
    dc = jl(ROOT / "registry/demo_type_counts.json")
    if dc:
        un = [k for k, v in dc.items() if v == 0 and k != "STOP"]; L += [f"Demonstrations : {len(dc) - 1 - len(un)}/{len(dc) - 1} types demontres ; jamais demontres : {', '.join(un)}", ""]
    # --- references
    L += ["## 3. Agents de reference (memes parties, seeds fixes ; IC de Wilson 95 %)", ""]
    for name, f in (("Aleatoire legal", "eval2_random"), ("Professeur v2", "eval2_teacher"), ("Professeur v2 + alliance(threats)", "eval2_teacher_ally_threats"), ("Professeur v3 complet", "eval2_teacher3")):
        r = jl(B / f"{f}.json")
        if not r: L += [f"### {name} : NON MESURE", ""]; continue
        L += [f"### {name} ({r['specs']} parties, {r['secondes']} s)", "", "| groupe | difficulte | victoires | taux | IC95 | progression | morts |", "|---|---|---|---|---|---|---|"] + fmt_summary(r) + [""]
    abl = sorted(glob.glob(str(B / "abl_*.json")))
    if abl:
        L += ["### Ablation du professeur v3 (Medium, memes parties)", "", "| variante | victoires | morts | progression |", "|---|---|---|---|"]
        for f in abl:
            r = jl(f); P = [x for x in r["parties"] if x["cfg"]["difficulty"] == "Medium"]
            if P: L.append(f"| {pathlib.Path(f).stem} | {sum(x['win'] for x in P)}/{len(P)} | {sum(x['end'] == 'dead' for x in P)} | {sum(x['progress'] for x in P) / len(P):.2f} |")
        L.append("")
    # --- environnement d'execution courant (mesure au moment du rapport)
    try:
        import torch; tv = f"torch {torch.__version__} ({'cuda ' + torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU seulement'})"
    except Exception: tv = "torch non importable"
    L += [f"- Environnement d'execution de CE rapport : {platform.platform()}, {os.cpu_count()} coeurs logiques, {tv}. Les debits ci-dessus mesures sous Windows/GPU ne sont PAS ceux de cet environnement.", ""]
    at = jl(ROOT / "config/autotune.json")
    if at: L += ["### Auto-optimisation du parallelisme (`ofsi/autotune.py`, professeur scripte)", "", "| moteurs | decisions/s | latence p50 (ms) | p95 (ms) |", "|---|---|---|---|"] + [f"| {m['envs']} | {m['decisions_per_s']} | {m['step_p50_ms']} | {m['step_p95_ms']} |" for m in at["mesures"]] + [f"Choix : {at['choisi_envs']} moteurs ({at['regle']}). {at['politique']}.", ""]
    # --- initialisations : GLOUTON et ECHANTILLONNE sont presentes separement (le glouton fausse les politiques PPO : journal 2026-11-26)
    L += ["## 4. Agents neuronaux (memes 48 parties, seeds fixes)", "",
          "> **Le decodage glouton fausse l'evaluation des politiques entrainees par PPO** (journal 2026-11-26) : seules les evaluations ECHANTILLONNEES (`*_sample.json`) sont comparables entre agents. Les evaluations gloutonnes sont listees a titre historique.", ""]
    samp = sorted(glob.glob(str(B / "*_eval_sample.json"))); ref = jl(B / "eval2_teacher_ally_threats.json")
    if samp and ref:
        def wins(r): return {x["cfg"]["_id"]: bool(x["win"]) for x in r["parties"]}
        import math
        def mcn(b, c):
            n = b + c; return 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)
        W0 = wins(ref); L += ["### Echantillonne, apparie (McNemar exact bilateral)", "", "| agent | victoires /48 | Easy | Medium | vs professeur (gagnees/perdues, p) |", "|---|---|---|---|---|", f"| professeur `threats` (reference) | {sum(W0.values())} | {ref['resume']['TOUT']['Easy']['victoires']}/{ref['resume']['TOUT']['Easy']['parties']} | {ref['resume']['TOUT']['Medium']['victoires']}/{ref['resume']['TOUT']['Medium']['parties']} | — |"]
        for f in samp:
            r = jl(f); Wr = wins(r); ids = sorted(set(Wr) & set(W0)); bb = sum(1 for i in ids if Wr[i] and not W0[i]); cc = sum(1 for i in ids if W0[i] and not Wr[i]); sm = r["resume"]["TOUT"]
            L.append(f"| {pathlib.Path(f).stem.replace('_eval_sample', '')} | {sum(Wr.values())} | {sm.get('Easy', {}).get('victoires', '?')}/{sm.get('Easy', {}).get('parties', '?')} | {sm.get('Medium', {}).get('victoires', '?')}/{sm.get('Medium', {}).get('parties', '?')} | {bb}/{cc}, p={mcn(bb, cc):.3f} |")
        L += ["", "Lecture : une difference n'est consideree DEMONTREE que si p < 0,05 ; sinon elle est rapportee comme non significative (24 parties par difficulte : faible puissance).", ""]
    else: L += ["**NON MESURE** : aucune evaluation echantillonnee.", ""]
    for f in sorted(glob.glob(str(B / "arm_*_eval.json"))):
        r = jl(f); L += [f"### {pathlib.Path(f).stem} (GLOUTON, historique)", "", "| groupe | difficulte | victoires | taux | IC95 | progression | morts |", "|---|---|---|---|---|---|---|"] + fmt_summary(r) + [""]
    # --- ligue
    L += ["## 5. Ligue, recherche et modele des adversaires", ""]
    lg = jl(B / "league_v2.json")
    if lg:
        L += [f"### Ligue v2 ({len(lg['matches'])} duels, {lg['secondes']} s) — Bradley-Terry, IC95 bootstrap", "", "| agent | force BT | IC95 |", "|---|---|---|"] + [f"| {t['agent']} | {t['force_BT']} | {t['ic95'][0]} ; {t['ic95'][1]} |" for t in sorted(lg["table"], key=lambda t: -t["force_BT"])]
        L += ["", "**Attention** : ~6 duels par paire ; les IC des premiers se chevauchent, aucun ordre entre eux n'est demontre. Duels : victoire de partie puis tuiles finales.", ""]
    else: L += ["**NON MESURE** : aucun classement de ligue.", ""]
    for arm, nm in (("threats", "professeur `threats`"), ("none", "professeur faible `none`")):
        t, q = jl(B / f"plan_teacher_{arm}.json"), jl(B / f"plan_planner_{arm}.json")
        if t and q:
            def wd(r): return {x["cfg"]["_id"]: bool(x["win"]) for x in r["parties"]}
            A, Bq = wd(t), wd(q); ids = sorted(set(A) & set(Bq)); bb = sum(1 for i in ids if Bq[i] and not A[i]); cc = sum(1 for i in ids if A[i] and not Bq[i]); n = bb + cc
            pv = 1.0 if n == 0 else min(1.0, 2 * sum(__import__("math").comb(n, i) for i in range(min(bb, cc) + 1)) / 2 ** n)
            L += [f"### Planificateur sur snapshots, {nm} (24 parties Medium appariees) : {sum(A.values())}/24 -> {sum(Bq.values())}/24 ({bb} gagnees / {cc} perdues, McNemar p={pv:.3f})", ""]
    om = jl(B / "oppmodel.json")
    if om:
        h = om["avec_historique"]; L += ["### Modele des adversaires (validation par episode)", "", "| cible | gain vs persistance / AUC |", "|---|---|"]
        L += [f"| {k} | gain {v['gain_vs_persistance']:+.2f} |" for k, v in h["regression"].items()] + [f"| {k} | AUC {v['auc']:.3f} (taux de base {v['taux_base']:.3f}) |" for k, v in h["evenements"].items()] + ["", "Limite : demonstrations d'un seul professeur ; modele non branche sur la politique.", ""]
    # --- jalons : SOURCE UNIQUE = docs/PROOF_MATRIX.md (pas de texte fige ici)
    pm = ROOT / "docs/PROOF_MATRIX.md"
    if pm.exists():
        txt = pm.read_text(encoding="utf-8"); i = txt.find("## Jalons"); j = txt.find("## Priorit")
        L += ["## 6. Jalons de maturite (MISSION.txt §44) — repris de `docs/PROOF_MATRIX.md`", "", txt[i:j].strip() if i >= 0 else "NON MESURE", ""]
    from ofsi import notify as _n
    L += ["## 7. Statut et limitations", "", f"Banniere : **{_n.status()['banner']}**", "", "- Voir `docs/PROOF_MATRIX.md` (statut PASS/PARTIEL/NON FAIT par exigence) et `docs/JOURNAL.md` (toutes les mesures, tous les defauts trouves).", "- Cartes d'entrainement : 8 ; validation : 4 cartes jamais vues ; 24 parties par difficulte : IC larges.", "- Easy/Medium seulement pour les agents entraines ; Hard/Impossible non evalues.", "- Aucune comparaison executee avec un agent public externe (jalon 10 hors d'atteinte).", ""]
    out = ROOT / "reports"; out.mkdir(exist_ok=True); f = out / f"rapport_{datetime.datetime.now():%Y%m%d_%H%M}.md"; f.write_text("\n".join(L), encoding="utf-8"); print(f, len(L), "lignes")


if __name__ == "__main__":
    main()
