# Matrice de preuves — MISSION.txt (état au 2026-11-26)

Légende : **PASS** = exigence satisfaite ET mesurée ; **PARTIEL** = une partie existe/est mesurée ; **NON FAIT** = aucun code ; **BLOQUÉ** = impossible avec les ressources actuelles (raison donnée).
Règle : un statut ne monte que sur une MESURE reproductible citée ; « le code existe » ne vaut jamais PASS pour une capacité d'intelligence. Fichier maintenu à la main : toute ligne cite sa preuve ou dit qu'il n'y en a pas.

| § | Exigence | Statut | Preuve / commande | Limites |
|---|---|---|---|---|
| 3 | Installation et matériel | PARTIEL (Linux : PASS reproductible) | Windows : `OpenFront-SI.ps1 doctor/repair` testés. Linux : `./ofsi.sh setup` depuis un CLONE VIERGE en 2 min, puis 30/30 scénarios PASS (même commit moteur `db8bf7c`) | `setup` non testé de bout en bout ; Linux sans GPU |
| 4 | Produit et structure | PARTIEL | arborescence du README | pas d'installateur testé |
| 5 | Sources et recherche | PARTIEL | moteur officiel épinglé `db8bf7c4` ; djmango/openfront-ai étudié non exécuté (licence absente) ; OpenFront_Agents non exécutable (LLM/compte) | pas de comparaison exécutée avec un agent public |
| 6 | Moteur headless | PASS | `selftest_snapshot.mts` : hash identique ; 30/30 scénarios sur Windows ET Linux | — |
| 7 | Haute performance | PARTIEL | 147,5 déc/s (Linux, professeur, 4 cœurs) ; 532 ticks/s World/100 bots (Windows) | audit `docs/PERF_AUDIT_PLAN.md` NON exécuté |
| 8 | Snapshots, futurs alternatifs | PASS | snapshot/restore identiques ; `counterfactual.py` : 1 défaite analysée | 1 seule défaite analysée |
| 9 | Benchmarks reproductibles | PARTIEL | `benchmarks/*.json`, 48 parties à seeds fixes | pas de protocole d'environnement figé automatique |
| 10 | Fidélité, tests différentiels | PARTIEL | moteur officiel non modifié ; déterminisme 3 exécutions + rejeu de défaite | pas de test différentiel contre un second moteur |
| 11 | Inventaire des mécaniques | PASS | `registry/mechanics.json`, `registry/engine_audit.json` | généré, à régénérer si le moteur change |
| 12–19 | Géographie, combat, économie, constructions, marine, commerce, diplomatie, défenses | PARTIEL | `registry/coverage_v2.md` : 19/19 intents valides par scénario à effet vérifié | PASS = l'action s'exécute, PAS que l'agent la maîtrise ; scénarios sur Onion seulement |
| 20 | Observations et actions | PASS | `space.py` 32 types + pointeurs, masques exacts ; 0 action illégale / 1 070 | information interne des nations non exposée (voulu) |
| 21 | Architecture multi-compétences | PARTIEL | `PolicyV2` 1,41 M param. (entités + grille + transformer + décodeur) | pas de modules spécialisés comparés ; ablations d'architecture NON faites |
| 22 | Préentraînement | PARTIEL | bc/ssl/both implémentés ; SSL en surapprentissage mesuré | aucune méthode ne dépasse l'imitation du professeur |
| 23 | Modèle du monde, contrefactuels | PARTIEL | `WorldHead` (SSL), `counterfactual.py` | pas utilisé pour la planification |
| 24 | Modèle individuel des adversaires | PARTIEL | `ofsi/rl2/oppmodel.py`, `test_oppmodel.py` 7/7, `benchmarks/oppmodel*.json` : AUC 0,81-0,95, gain +22-42 % vs persistance à h=20, ablation anti-fuite réfutée | démonstrations d'UN seul professeur ; NON branché sur la politique → aucun gain de jeu démontré |
| 25 | Planification hiérarchique / recherche | PARTIEL | `ofsi/rl2/planner.py` (recherche sur snapshots exacts, validation des snapshots, abandon explicite), `test_planner.py` 4/4 ; essais appariés 24 parties Medium : professeur faible `none` 2/24 → 9/24 avec recherche (7/0, **p=0,016**) ; professeur `threats` 12/24 → 13/24 (p=1,0) (`benchmarks/plan_*.json`) | la recherche corrige un professeur lacunaire mais ne dépasse pas le bon professeur (9 < 12) ; profondeur fixe, pas hiérarchique ; jusqu'à 5,6 % de snapshots invalides (limite du moteur) ; coût de calcul très élevé |
| 26 | Agents de référence, professeurs | PASS | teacher v2+alliance : Easy 23/24, Medium 9/24 ; aléatoire 0/48 | teacher v3 : résultat négatif documenté |
| 27 | Curriculum adaptatif | PARTIEL | `Curriculum` (7 étapes) dans `ppo2.py` | jamais démontré comme utile (aucun run n'a passé Easy) |
| 28 | Arène, self-play massif | PARTIEL | `league.py` : ligue de 5 agents, 60 duels valides (59), Bradley-Terry + IC bootstrap (`benchmarks/league_v2.json`) ; 2 défauts corrigés (glouton, `spawn_failed`) | 6 duels par paire : seuls « aléatoire dernier » et « PPO v2 < autres » sont établis ; pas de self-play d'entraînement ; pas de ligue à l'échelle |
| 29 | Apprentissage par renforcement | PARTIEL | PPO ancré (`arm_B_anchor`, échantillonné, 48 parties appariées) : 31/48 ; puis `arm_C_medium` 33/48 = parité avec le professeur (32/48, p=1,0) ; confirmation sur 96 parties Medium neuves : professeur 35, champion 36, candidat à ancrage faible 39 (p=0,72), 2 cycles d'orchestrateur à ancrage fort : 13/48 contre 17/48 (p=0,48) ; rien de significatif ; vs imitation seule 26/48 (p=0,27, non significatif) ; glouton catastrophique (6/48) ; PPO v2 sans ancrage 13/48 (p<0,001 vs ancré) | aucun agent entraîné ne DÉPASSE son professeur ; amélioration vs imitation non démontrée ; 1 graine |
| 30 | Apprentissage en temps réel | NON FAIT | — | — |
| 31 | Mémoire et données | PARTIEL | démonstrations `data/demos_v3` (60 056 décisions) | pas de mémoire de parties/replay buffer prioritaire |
| 32 | Analyse des défaites | PARTIEL | 1 analyse contrefactuelle, ablation du professeur v3 | échantillon minuscule |
| 33 | Découverte stratégique, évolution | PARTIEL | `ofsi/rl2/evolve.py` : (1+5)-ES sur 8 paramètres du professeur, 6 générations, test final sur 48 parties jamais vues (`benchmarks/evolve_final.json`, `evolve_gens.jsonl`) : évolué 22/48 vs défaut 24/48, p=0,83 | AUCUNE stratégie meilleure démontrée (malédiction du vainqueur observée : 15/24 en recherche → 22/48 en test) ; espace de recherche restreint aux paramètres d'un script, pas de découverte de comportements nouveaux |
| 34 | Optimisation automatique des modèles | PARTIEL | `ofsi/autotune.py` + `./ofsi.sh autotune` : mesure le débit pour N moteurs, empreinte matérielle, `config/autotune.json` (4 cœurs : 2→21, 4→36, 8→55, 12→62, 16→68 déc/s, professeur scripté) | optimise seulement le NOMBRE DE MOTEURS (pas l'architecture, lr, batch) ; mesuré avec professeur scripté, pas avec réseau ; optimum à la borne testée (16) |
| 35 | Ordonnanceur de ressources | PARTIEL | `ofsi/scheduler.py` + `test_scheduler.py` 8/8 (vrais sous-processus : budget de cœurs jamais dépassé, priorités, blocage RAM, STOP, échec isolé) ; `memguard.py` | NON câblé dans l'orchestrateur ni dans `ofsi.sh` ; pas de gestion GPU/VRAM ; pas d'ajustement dynamique à la charge d'autres applications ; sur 4 cœurs il ne fait que sérialiser |
| 36 | GPT facultatif | PASS (absent par choix) | aucune dépendance LLM | — |
| 37 | Tableau de bord, données réelles | PARTIEL | `dashboard.py` ; test UI automatisé Chromium headless `ofsi/test_dashboard_ui.js` 8/8 (bannière jamais « validée » sans preuve, rejeu, canvas, 0 erreur JS) ; capture visuelle relue | pas de tests des boutons stop/pause en UI ; températures/GPU non mesurés ici |
| 38 | Observer, rejouer | PARTIEL | `ofsi/replay.py` (enregistrement décision par décision depuis le moteur) + visualiseur du tableau de bord (liste, lecture/pause, curseur, tuiles/troupes/or/actions par image) ; rejeu déterministe | rendu grossier (grille 40×40, 5 classes), pas de rejeu tick par tick ni de vue des unités ; un seul rejeu de démonstration enregistré |
| 39 | Arène manuelle, UX un clic | PARTIEL | `play.py` (32 lignes), `OpenFront-SI.ps1` | `train/stop/setup/benchmark/evaluate/skills` non validés de bout en bout |
| 40 | Persistance, robustesse, diagnostic | PARTIEL | checkpoints SHA-256, STOP/PAUSE, reprise `--resume`, bruit stdout toléré | pas de test de reprise après crash prouvé |
| 41 | Protocole scientifique | PARTIEL | IC de Wilson, McNemar, protocole écrit avant résultat | 1 graine par bras ; 24 parties/difficulté |
| 42 | Champion, plateaux | PARTIEL | registre `runs/_orch/champion.json` + historique, promotion par McNemar apparié (testée), `notify` détecte plateaux/régressions | aucun champion entraîné ne dépasse le professeur |
| 43 | Orchestration autonome | PARTIEL | `ofsi/orchestrator.py` + `./ofsi.sh orchestrate` : cycles entraîner-candidat-ancré → évaluer échantillonné → promotion McNemar → notification ; `test_orchestrator.py` 5/5 (promotion, non-promotion, candidat pire, reprise, STOP) ; 1 cycle miniature RÉEL (1 MAJ, 4 parties) | aucun cycle à budget réel exécuté par l'orchestrateur ; une seule stratégie d'entraînement (PPO ancré) ; pas de self-play ni d'ajustement automatique de la difficulté |
| 44 | Critères de maturité | voir ci-dessous | — | — |
| 45 | Notifications, rapport | PARTIEL | `ofsi/notify.py` + `ofsi/test_notify.py` (15/15 PASS : plateau, régression, record de débit, divergence, disque, dédup, bannière jamais « VALIDÉE » sans `docs/validation.json` all_pass) ; intégré au tableau de bord (`/api/status`, `/api/notifications`), testé sur données réelles ; `report.py` | « nouveau champion » et toast Windows non testés (Linux) ; rapport automatique complet non vérifié |
| 46 | Livrables | PARTIEL | README, DEVELOPER, JOURNAL | voir lignes ci-dessus |

## Jalons §44 (niveau atteint, sans embellissement)
0 PASS · 1 PASS · 2 PASS · 3 PASS (fidélité + débit mesurés, audit complet non fait) · 4 PARTIEL (arène/références oui, ligue peu exécutée) · 5 PASS (réseaux fonctionnels, 0 action illégale) ·
**6 NON DÉMONTRÉ** (le PPO ancré atteint la parité avec le professeur ; `arm_C_medium` 33/48 vs imitation 26/48, p=0,12 : amélioration non significative) · 7 PARTIEL · 8 PARTIEL (mécaniques exécutables, maîtrise non mesurée) · 9 NON · 10 NON.

**Bannière honnête : VALIDATION PARTIELLE — LIMITATIONS IDENTIFIÉES.** Cibles §44 (>99 % Easy, >98 % Medium, >95 % Hard) : NON atteintes (professeur Easy 96 %, Medium 38 %, Hard ~6 % ; meilleur réseau, échantillonné : `arm_C_medium` Easy 96 %, Medium 42 %).

## Priorités déduites de la matrice (ordre de travail)
1. Jalon 6 : obtenir un apprentissage RL qui DÉPASSE le professeur (PPO ancré = parité ; prochaine étape : entraînement sur Medium depuis `arm_B_anchor`).
2. §24 : brancher le modèle d'adversaires sur la politique et mesurer le gain de jeu ; §25 : gain de la recherche non démontré (essai à faible puissance).
3. §35 : câbler l'ordonnanceur (utile surtout avec plus de cœurs/GPU) ; §43 : exécuter de vrais cycles d'orchestration ; §33 : évolution/découverte stratégique (aucun code).
4. §45 : (fait en partie) ajouter la détection de nouveau champion et tester le toast Windows.
5. §7 : audit de performance du plan.
