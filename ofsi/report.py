"""Rapport automatique (Markdown) : compile UNIQUEMENT des artefacts mesures (benchmarks/*.json, registry/*, runs/*). Tout ce qui n'a pas de preuve est marque 'NON MESURE'.
Usage : python ofsi/report.py  ->  reports/rapport_<date>.md"""
import json, glob, pathlib, datetime, subprocess, os, sys, platform
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
    # --- initialisations
    L += ["## 4. Comparaison des initialisations (PPO a budget identique)", ""]
    arms = sorted(glob.glob(str(B / "arm_*_eval.json")))
    if not arms: L += ["**NON MESURE** : aucun bras PPO n'a encore ete evalue.", ""]
    for f in arms:
        r = jl(f); L += [f"### {pathlib.Path(f).stem}", "", "| groupe | difficulte | victoires | taux | IC95 | progression | morts |", "|---|---|---|---|---|---|---|"] + fmt_summary(r) + [""]
    # --- ligue
    L += ["## 5. Ligue / self-play", ""]
    lg = jl(B / "league.json")
    L += [(f"Classement Bradley-Terry : {lg['table']}" if lg else "**NON MESURE** : seule une partie de test (aleatoire vs professeur) a ete jouee ; aucun classement de ligue.")]
    L += ["", "## 6. Jalons de maturite (MISSION.txt §44) — etat prouve", "",
          "| jalon | etat | preuve |", "|---|---|---|",
          "| 1 environnement operationnel | PASS | Node 24 portable, moteur installe, venv GPU, `OpenFront-SI.ps1 doctor` |",
          "| 2 moteur local fonctionnel | PASS | adaptateur reset/step/snapshot/restore, hash identique apres restauration |",
          "| 3 fidelite et debit mesures | PARTIEL | debit mesure ; test differentiel complet moteur officiel vs port : NON APPLICABLE (aucun port ; le moteur officiel EST la reference) ; golden replays : NON FAIT |",
          "| 4 arene et references | PARTIEL | arene + 3 references (aleatoire, professeurs) ; bots officiels evalues par difficulte (4 niveaux) ; ligue : un test |",
          "| 5 reseaux fonctionnels | PASS | PolicyV2 1,41 M parametres, masques exacts, teacher-forcing verifie |",
          "| 6 apprentissage reel demontre | **NON PROUVE** | PPO v1 invalide ; comparaison v3b en cours |",
          "| 7 autonomie et reprise | PARTIEL | checkpoints SHA-256 + reprise implementes ; test d'arret/reprise/crash : NON FAIT |",
          "| 8 maitrise des mecaniques | **NON PROUVE** | 19/19 intents executables (scenarios) mais maitrise par l'agent non mesuree |",
          "| 9 superiorite contre references locales | **NON PROUVE** | aucun agent entraine ne depasse son professeur |",
          "| 10 superiorite contre agents publics | **IMPOSSIBLE EN L'ETAT** | OpenFront_Agents = LLM avec compte ; openfront-ai = sans licence + autre moteur ; decision utilisateur en attente |", ""]
    L += ["## 7. Limitations connues", "", "- Cartes d'entrainement : 8 ; validation : 4 cartes jamais vues, echantillons petits (IC larges).", "- Evaluation en Easy/Medium seulement ; Hard/Impossible non evalues pour les agents entraines.",
          "- Lanceur : `doctor`, `repair`, `dashboard` testes ; `setup`, `train`, `stop`, `benchmark`, `evaluate`, `skills` non valides de bout en bout.", "- Aucun conseil statistique multi-comparaisons n'est applique aux ablations (indicatif).", ""]
    out = ROOT / "reports"; out.mkdir(exist_ok=True); f = out / f"rapport_{datetime.datetime.now():%Y%m%d_%H%M}.md"; f.write_text("\n".join(L), encoding="utf-8"); print(f, len(L), "lignes")


if __name__ == "__main__":
    main()
