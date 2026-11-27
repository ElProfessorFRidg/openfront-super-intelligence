# Portabilité cloud ↔ PC et critères de bascule (état au 2026-11-27)

Machines : **cloud** = Xeon 2,1 GHz, 4 cœurs, 15 Go, sans GPU (AMX bf16) · **PC** = Core Ultra 7 155H (16 cœurs / 22 threads), RTX 3050 6 Go, 32 Go, Windows 11.
Ce document sépare MESURÉ (avec source) et ESTIMÉ.

## 1. Transport des checkpoints (sans perdre les acquis)
| exigence | état | preuve |
|---|---|---|
| PC → cloud : charger un checkpoint produit sur GPU | **PROUVÉ** | `runs/init_bc`, `arm_B_bc`, `arm_D_both`… (produits sous Windows/CUDA) chargés et joués sur CPU ici (évaluations 48 parties) |
| cloud → PC : charger un checkpoint produit sur CPU | NON TESTÉ sur CUDA (standard `map_location`) ; format identique, tenseurs CPU, SHA-256 | `ofsi/rl2/ckpt_check.py` : « tenseurs_sur_cuda=false » |
| intégrité de bout en bout | PROUVÉ | `.sha256` vérifié à chaque `ckpt.load` ; corruption d'1 octet détectée (test) |
| corruption par Git/Windows (fins de ligne) | PRÉVENU | `.gitattributes` : `*.pt`/`*.npz` binaires, `*.sha256` sans conversion |
| reprise d'un entraînement | PROUVÉ (même machine) | `ppo2.py --resume` : arrêt à la MAJ 2, reprise à 3–4, décisions cumulées 96 → 128, optimiseur + curriculum + `env_steps` restaurés (test réel) |
| reprise inter-machines | NON TESTÉE de bout en bout ; l'optimiseur AdamW est restauré par `load_state_dict` (déplacement automatique des états vers le dispositif des paramètres) | à valider au 1er transfert : `ckpt_check.py` puis 2 MAJ avec `--resume` |
| traçabilité | AJOUTÉE | chaque nouveau checkpoint embarque `meta` (torch, dispositif, plateforme, commit git, date) ; les anciens n'en ont pas |

**Procédure de transfert** : (1) `git push` depuis la machine source (les `ckpt_latest.pt` + `.sha256` sont versionnés) ; (2) `git pull` sur l'autre ; (3) `python ofsi/rl2/ckpt_check.py runs/<run>/ckpt_latest.pt` ; (4) `ppo2.py --name <run> --resume` (même dossier `runs/<run>`) ou `--init <ckpt>` pour repartir d'un autre run. Les checkpoints intermédiaires `ckpt_uNNNNNN.pt` sont ignorés par git (copier à la main si utile).

## 2. Les résultats ne se transportent pas au bit près
Mesuré (256 états de validation, `init_bc` et `arm_C_medium`) : fp32 (CPU) contre bf16 (comme CUDA) → |Δ log-prob| moyen 0,011–0,013 (max 0,17–0,23) ; décodage glouton identique dans 99,2–99,6 % des états. Donc une évaluation sur le GPU est **statistiquement équivalente mais pas identique** : une partie peut diverger (le jeu est chaotique, cf. journal).
**Règle** : ne jamais mélanger deux machines (ni deux types de calcul) dans une même comparaison appariée ; si l'on change de machine, ré-évaluer le champion de référence sur la nouvelle machine avant toute comparaison.

## 3. Pourquoi / quand passer en local — chiffres
Mesures (mêmes champs `collect_s`, `train_s`, `decisions_per_s` des `metrics.jsonl`) :
| run | machine | MAJ | déc/s (médiane) | collecte (s) | entraînement (s) | % entraînement |
|---|---|---|---|---|---|---|
| arm_B_bc | PC + GPU, 8 moteurs (CPU plafonné, mode MSI) | 235 | 20,6 | 23,5 | 1,5 | 6 % |
| arm_D_both | PC + GPU, 8 moteurs | 155 | 34,1 | 13,6 | 1,4 | 9 % |
| arm_C_ssl / arm_A_random | PC + GPU, 8 moteurs | 60 / 38 | 52,2 / 51,8 | 8,4 / 8,5 | 1,4 | 14 % |
| arm_B_anchor | cloud 4 cœurs, 6 moteurs | 157 | 17,6 | 13,4 | 9,3 | 41 % |
| arm_C_medium | cloud 4 cœurs, 6 moteurs | 313 | 18,1 | 11,8 | 9,3 | 44 % |
Benchmarks PC (`benchmarks/gpu_vs_cpu.json`) : encodeur à attention (4 couches, d=256) CPU 2 619 ms/pas contre CUDA 165 ms (**15,8×**), inférence 137 → 5 ms (**27×**) ; MLP 1024 : 6,2× à l'entraînement.
**Lecture** : (a) aujourd'hui, à taille de modèle actuelle (1,41 M de paramètres), le PC donne ≈ **2–3×** de décisions/s (34–52 contre 18 déc/s) et divise l'entraînement par ≈ **6,6×** (1,4 s contre 9,3 s) ; (b) la simulation reste le poste dominant des deux côtés (collecte 56–94 % du temps), donc le gain ne dépasse pas ≈ 2–3× tant que le modèle ne grossit pas ; (c) pour un modèle plus grand (attention plus profonde, d plus large), le CPU devient inutilisable (×16 à ×27) : c'est là que le GPU est INDISPENSABLE.
**Déclencheurs de bascule (je vous préviens dès qu'un seul est vrai)** : (1) un pas d'entraînement CPU dépasse ≈ 30 s/MAJ ou l'entraînement dépasse 60 % du temps (modèle plus gros) ; (2) une campagne planifiée dépasse ≈ 3 jours de cloud pour un gain mesuré de ≥ 2× en local ; (3) besoin d'évaluer Hard/Impossible à grande échelle (≥ 200 parties/agent) ; (4) montée en taille du réseau (§21) non faisable sur CPU. **Aucun de ces seuils n'est atteint aujourd'hui** : on reste sur le cloud.
Limites des chiffres : débits PC mesurés avec un plafond de fréquence CPU variable (20–52 déc/s selon la charge) ; aucun benchmark moteur cloud « World/100 bots » comparable ; estimations ≠ mesures.

## 4. À faire au passage en local (anticipation)
- Conserver ≈ 4–6 Go pour Windows : `memguard` (0,45 Go/moteur + 3,5 Go) autorisera ≈ 40 moteurs sur 32 Go, mais la CPU sature vers 16 moteurs (532 t/s mesuré à 16, 503 à 22) : viser 12–16 moteurs ; `./ofsi.sh autotune` (à porter en PowerShell) re-mesure sur place.
- Entraînement sur CUDA en bf16 autocast + TF32 (déjà le défaut de `ppo2.py` quand `cuda` est disponible).
- Re-vérifier le champion de référence sur la nouvelle machine (règle du § 2).
