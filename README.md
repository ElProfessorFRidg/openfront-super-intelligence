# OpenFront Super Intelligence — usine locale d'apprentissage

Projet **local et isole** (aucune connexion aux serveurs officiels, aucune cle API, aucun compte). Il fait jouer le moteur OpenFront officiel (epingle, AGPL-3.0) a des agents,
mesure leur niveau de facon reproductible et entraine un reseau neuronal par apprentissage par renforcement.

> **Etat honnete** : voir `docs/JOURNAL.md` (journal date, avec toutes les mesures) et `reports/` (rapport automatique). A ce jour, **aucun agent entraine ne depasse son professeur** ;
> la comparaison des initialisations est en cours ; ligue et self-play ne sont que testes. Ne rien lire dans ce README comme une promesse de niveau.

## Demarrage (Windows 11, PowerShell, depuis ce dossier)

```powershell
.\OpenFront-SI.ps1 doctor      # diagnostic en lecture seule : GPU/CUDA, RAM, disque, frequence CPU, integrite des checkpoints
.\OpenFront-SI.ps1 dashboard   # tableau de bord local http://127.0.0.1:8765 (loopback uniquement)
.\OpenFront-SI.ps1 train       # lance/reprend un entrainement PPO en arriere-plan (nom optionnel : train mon_run)
.\OpenFront-SI.ps1 stop        # arret propre : chaque entrainement sauvegarde un checkpoint puis s'arrete
.\OpenFront-SI.ps1 repair      # resynchronise l'adaptateur sans toucher aux checkpoints
```

Valide de bout en bout : `doctor`, `repair`, `dashboard`. **Non valides de bout en bout** : `setup`, `train`, `stop`, `benchmark`, `evaluate`, `skills` (voir `docs/JOURNAL.md`).
Fermer le navigateur ou le terminal n'interrompt pas un entrainement lance ; il s'arrete par `stop` (fichier `runs/<nom>/STOP`) ou se met en pause (`PAUSE`).

## Demarrage Linux / macOS

```bash
./ofsi.sh setup      # idempotent : Node 24 local, moteur epingle, venv Python (torch CPU), smoke test
./ofsi.sh doctor     # diagnostic en lecture seule (SHA-256 des checkpoints inclus)
./ofsi.sh dashboard  # http://127.0.0.1:8765
./ofsi.sh train mon_run runs/arm_B_anchor/ckpt_latest.pt   # PPO ancre (recette validee : voir docs/JOURNAL.md)
./ofsi.sh evaluate runs/arm_C_medium/ckpt_latest.pt        # eval 48 parties ; ajouter OFSI_ENVS=N pour le parallelisme
```
Important : evaluer une politique PPO en mode **echantillonne** (`eval2.py --sample`) ; le decodage glouton la fausse (voir journal 2026-11-26). Matrice de preuves par exigence : `docs/PROOF_MATRIX.md`.

## Materiel

Teste sur MSI Prestige 14 (Core Ultra 7 155H, 32 Go, **RTX 3050 6 Go**). Le GPU n'est visible que **sur secteur** et en mode graphique discret.
Si les calculs semblent lents : `doctor` signale un plafond de frequence CPU (mode constructeur « silencieux/economie » : MSI Center -> Extreme Performance).
Sans GPU, le petit reseau reste utilisable ; le reseau v2 (attention) est inutilisable sur CPU (2,3 s par pas d'entrainement mesure).

## Ce qu'il contient

| dossier | role |
|---|---|
| `vendor/openfront-engine` | moteur officiel (commit `db8bf7c4`) — **reference de verite**, non modifie |
| `adapter/` | demon Node (reset/step/snapshot/restore/observations/candidats) au-dessus du moteur |
| `ofsi/` | clients Python, arene, scenarios de competence, tableau de bord |
| `ofsi/rl2/` | espace d'actions v2 (32 types + pointeurs), reseau, PPO, preentrainement, ligue, contrefactuels |
| `registry/` | registre des mecaniques et matrice de preuves (generes depuis le moteur) |
| `benchmarks/`, `runs/`, `data/` | resultats mesures, checkpoints (SHA-256), demonstrations |
| `runs/_archive_invalides/` | checkpoints INVALIDES conserves comme preuves (ne jamais les utiliser) |

## Desinstallation propre

Supprimer le dossier du projet. Rien n'est installe hors de lui (Node 24 portable dans `tools/`, venv dans `.venv-gpu/`). Les modeles sont dans `runs/` : sauvegardez-les avant si besoin.

## Licences

Moteur et agents derives : AGPL-3.0 (assets CC BY-SA 4.0). `djmango/openfront-ai` n'a **aucune licence** : etudie, jamais copie. `OpenFront_Agents` necessite un LLM/compte : non execute.
