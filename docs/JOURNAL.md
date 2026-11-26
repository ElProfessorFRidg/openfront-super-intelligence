# Journal de décisions et de mesures

Faits mesurés uniquement. Toute mesure indique la machine où elle a été prise.

## 2026-11-25 — Jalon 1 en cours (environnement)

### Machine locale (mesuré)
- CPU : Intel Core Ultra 7 155H, 16 cœurs / 22 threads. RAM 31,7 Go.
- Disque C: ~13,5 Go libres après installation (**contrainte forte** : checkpoints et replays à quota strict).
- GPU : RTX 3060 Laptop annoncée. `nvidia-smi` refuse l'accès sans droits admin, donc **non vérifié**. PyTorch installé = 2.6.0+cpu (CUDA indisponible). À corriger avant l'entraînement GPU.
- Outils : Git 2.53, Python 3.11.6, Rust 1.93 MSVC, CMake, gcc (WinLibs), Node 22.22.2 système.

### Sources (épinglées)
| Projet | Commit | Licence | Décision |
|---|---|---|---|
| openfrontio/OpenFrontIO | db8bf7c4 (2026-11-25) | AGPL-3.0 (code), CC BY-SA 4.0 (assets) | Moteur de référence. Exécuté en local, adaptateur écrit par nous. |
| djmango/openfront-ai | 47453634 (2026-09-28) | **Aucun fichier LICENSE** (droits réservés par défaut) | Étudié et utilisé comme adversaire/comparaison. **Aucun code copié.** |
| PeytonWDYM/OpenFront_Agents | 334ee54b (2026-09-30) | AGPL-3.0 (fork du moteur) | Étudié, adversaire. Réutilisation possible sous AGPL seulement après vérification. |

Consigne utilisateur : ces projets servent de références et d'adversaires, jamais d'architecture imposée. Plusieurs architectures radicalement différentes seront entraînées et comparées; une architecture n'est retenue que si sa supériorité est mesurée, reproductible et statistiquement crédible.

### Environnement Node
- Le moteur exige Node >=24.15 <25 et npm >=12.1. Le système a Node 22.
- Node 24.22.3 portable installé dans `tools/node24/` (zip officiel, SHA256 vérifié). npm 12.2.3 installé dedans. L'installation système n'est pas modifiée.
- Activation : `$env:PATH="<racine>\tools\node24\node-v24.22.3-win-x64;$env:PATH"`.

### Moteur headless (mesuré, CPU local, 1 thread)
- `tests/perf/fullgame/FullGamePerf.ts`, carte World, 100 bots + nations (140 joueurs), 600 ticks de jeu.
- 162–177 ticks/s, p50 4,9 ms, p95 10,9 ms, p99 16,2 ms par tick.
- Déterminisme : hash final identique sur 3 exécutions (16691325426847732 au tick 800).
- Limite : ceci est un test de perf du moteur seul, pas encore l'interface reset/observe/step.

### Prochaines étapes
1. Lire `GameRunner`, `Executor`, schémas d'intents : inventaire des mécaniques (registre).
2. Écrire l'adaptateur headless (reset/observe/legal_actions/step/snapshot/restore/result).
3. Installer PyTorch CUDA (vérifier le GPU sans admin) ou documenter le fallback CPU.
4. Évaluer openfront-ai et OpenFront_Agents comme adversaires dans les mêmes conditions.

## 2026-11-25 — Registre des mécaniques v0 (généré)
- `adapter/scripts/gen_registry.mts` → `registry/mechanics.json` (commit moteur db8bf7c4). Exécution : `adapter\run_ts.ps1 scripts/gen_registry.mts <sortie>`.
- 25 intents (dont 5 d'administration de lobby exclus de l'espace d'actions IA : kick_player, toggle_pause, update_game_config, toggle_game_start_timer, mark_disconnected; emoji/quick_chat = communication).
- Difficulté officielle = 4 niveaux (Easy/Medium/Hard/Impossible). Les 9 niveaux demandés seront des niveaux INTERNES calibrés par tournoi, non assimilés aux niveaux officiels.
- 148 cartes officielles, 16 types d'unités (dont Train, Factory, MIRV, SAM).
- Note de build : les jonctions Windows cassent la résolution des paquets @openfront/* ; `adapter/run_ts.ps1` copie `adapter/` dans `vendor/openfront-engine/osi/` (artefact non versionné) avant exécution.
- Le registre n'est PAS encore la matrice de couverture complète : il liste actions/enums, pas encore les règles, bâtiments niveau par niveau, ni les scénarios de test.

## 2026-11-25 — Adaptateur headless v0 + test de snapshot (mesuré)
- `adapter/env.mts` (classe OFEnv) : reset / stepTick(intents) / snapshot / restore, au-dessus du `GameRunner` officiel. Aucun moteur réécrit.
- Découvertes moteur : intents = `StampedIntent` avec `clientID` ; agents = joueurs « humains » déclarés dans `gameStart.players` (clientID 8–10 alphanum) ; le `spawn` est un intent exécuté 1 tick plus tard, valable seulement s'il est émis pendant la phase de spawn ; légalité du spawn = `getSpawnTiles` (tuile non possédée, terre, non impassable). Le moteur fournit déjà snapshot/restore officiels (`packages/engine/src/snapshot/`).
- `adapter/scripts/selftest_snapshot.mts` (carte World, 2 agents + 50 bots + nations, seed selftest01) : snapshot au tick 202+150, 598 915 octets ; replay de 300 ticks avec les mêmes intents depuis la restauration ⇒ **hash identique** (9862040910910476) et tick identique (652). Les agents possèdent bien du territoire (52→60 tuiles), donc le test exerce leurs actions.
- Bug de test trouvé et corrigé : une première version lisait l'ancienne instance de jeu après restore (comparaison triviale) ; seule la version corrigée est retenue comme preuve.
- LIMITES : un seul scénario, une seule carte, 2 agents, actions scriptées limitées à `attack`. Ce n'est PAS encore le test différentiel complet, ni la couverture des 25 intents, ni un test sur plusieurs seeds/cartes. Pas encore de protocole IPC pour Python ni d'observations.

### Prochaines étapes (ordre)
1. Étendre l'adaptateur : sérialisation des observations (tuiles/joueurs/unités), masques d'actions légales via les `buildableUnits`/`PlayerActions` du moteur, résultat de partie.
2. Démon Node avec protocole JSON-lines/binaire pour Python; benchmark multi-environnements (1…N workers).
3. GPU : vérifier la RTX 3060 (nvidia-smi bloqué sans admin) et installer PyTorch CUDA, sinon fallback CPU documenté.
4. Agents de référence (aléatoire légal, expansionniste, bots officiels) + arène + premier Elo.
5. Évaluer openfront-ai / OpenFront_Agents comme adversaires (sans copier le code d'openfront-ai : pas de licence).

## 2026-11-25 — GPU : NON DISPONIBLE sur cette machine (mesuré)
- `Win32_VideoController` ne liste que « Intel(R) Arc(TM) Graphics » (pilote 32.0.101.8831). `nvcuda.dll`/`nvml.dll` existent, mais `cuInit(0)` (via ctypes) renvoie **100 = CUDA_ERROR_NO_DEVICE** et le nombre de périphériques CUDA est 0.
- Conclusion : la RTX 3060 Laptop annoncée dans MISSION.txt n'est PAS visible ici (absente, désactivée ou autre machine). Aucune mesure GPU ne sera revendiquée. Entraînement en CPU (PyTorch 2.6.0+cpu). Options futures à évaluer sur mesures : PyTorch XPU (Intel Arc iGPU, mémoire partagée) ; ou activation du GPU NVIDIA par l'utilisateur.
- Observation v0 (adapter/observe.mts) : avec grille d'ownership 129x65, 13,5 ms/appel (trop lent : à rendre incrémental). Légalité de construction exige une tuile ; masques par candidats de tuiles interrogés auprès du moteur (`playerActions`).

## 2026-11-25 — Pipeline Python↔Node↔moteur + benchmark parallèle (mesuré, CPU local)
- `adapter/daemon.mts` (JSON-lines) + `ofsi/client.py` : reset/step/observe/legal/legal_at/spawn_candidates/snapshot/restore/result. `adapter/sync_adapter.ps1` avant usage.
- Test IPC (World, 2 agents, 50 bots) : reset 2,6 s ; 142–149 ticks/s ; restore + replay 100 ticks => hash identique à travers l'IPC.
- Benchmark `ofsi/bench_parallel.py World 100 600 1,2,4,8,12,16,22` (100 bots + nations, agents 2, pas de décisions) → `benchmarks/parallel_World_100bots.json` :
  1 env 114 t/s ; 2 : 218 ; 4 : 346 ; 8 : 430 ; 12 : 512 ; **16 : 532 (pic)** ; 22 : 503 (régression). Réglage par défaut retenu : 16 workers.
- Limites : mesure courte (600 ticks/env), une seule carte, sans inférence réseau. Les parties/heure dépendent de la durée réelle d'une partie : NON encore mesurée.

## 2026-11-25 — Première partie complète jouée via le pipeline (mesuré)
- Carte World, 30 bots + nations par défaut (Medium), 2 agents scriptés `expansion_v0` (ofsi/agents.py, NON entraîné), seed play00001.
- Durée d'une partie : **13 512 à 15 402 ticks** (deux runs, résultats différents car l'agent a été corrigé entre-temps) ; 95–97 s de temps réel mono-env, observation à chaque décision incluse.
- Sémantique vérifiée : `attack.troops` est un nombre ABSOLU de troupes ; 45 % des troupes → 52 à 4 189 tuiles en 300 ticks. Les deux agents ont fini éliminés (pic ≈ 8 000 tuiles vers t=3 000, puis effondrement : sur-extension face aux nations Medium).
- Bug de mon agent corrigé : un test `tick % 10` ne tombait jamais sur les ticks de décision (203, 213…), donc la 1re partie « idle » ne prouve rien sur la qualité d'un agent.
- Estimation (calcul à partir de mesures, pas mesure directe) : 532 ticks/s agrégés ÷ ~14 000 ticks/partie ≈ 0,038 partie/s ≈ ~135 parties/heure sur World/30 bots, hors inférence réseau. Donc ~1 000 parties par nuit de 8 h pour cette configuration : l'objectif exploratoire « milliers à dizaines de milliers par nuit » n'est PAS atteint sur World ; à re-mesurer sur cartes plus petites et parties plus courtes.

## 2026-11-25 — Arène v0, cache de cartes, construction (mesuré)
- Onion (512x512) : partie ≈ 4 700–13 600 ticks ; ≈ 2 300–2 600 ticks/s mono-env en début de partie. Reset après le 1er : **0,01 s** (cache de cartes statiques dans le démon), 1er reset ≈ 1,9 s (démarrage Node+tsx).
- `ofsi/arena.py` : 16 workers, **1 004 parties/h** sur Onion (10 bots, spawn de processus inclus). Baseline `ExpansionAgent` (scripté, non entraîné) : **0/8 victoires en Easy et 0/8 en Medium** (IC95 [0 ; 0,32], échantillon très petit). Fichier : benchmarks/arena_ExpansionAgent_Onion.json.
- Économie observée : ≈ 100 or/tick de base ; City 125 000, Defense Post 50 000, Port/Factory 125 000, Warship 250 000, SAM 1,5 M, Silo 1 M, Atom 750 k, H-bomb 5 M, MIRV 25 M.
- `build_tiles` (adaptateur) : tuiles légales vérifiées par le moteur ; City construite avec succès (or 200 000 → 77 000). Port : aucune tuile trouvée dans l'échantillon (côte requise / sondage limité). Le CHOIX final de tuile est scripté en v1 (APPROXIMATION étiquetée), à remplacer par un module de placement appris.
- Bug corrigé : échappement `"\n"` cassé par un script de patch (client.py) → remplacé par chr(10).

## 2026-11-25 — Premier pipeline d'apprentissage (PPO v1) + tableau de bord + couverture (mesuré)
- Code : `ofsi/rl/spec.py` (obs 113 dim, 20 types d'actions factorisés + fraction 5 bins, masques), `vecenv.py` (N processus Node, reset auto, récompense : victoire +2, mort −1, façonnage potentiel = part de terre ×2), `ppo.py` (PPO masqué, GAE, curriculum 6 étapes Onion Easy→Impossible, 20 % de consolidation, checkpoints atomiques SHA256, reprise, STOP/PAUSE par fichier).
- Run `ppo_v1` (16 envs, MLP 2×256, CPU, 4 threads torch), lancé en arrière-plan : à l'update 25 le retour moyen passe de −1,00 à −0,17 ; **taux de victoire 0 %** ; ~130–176 décisions/s (1 décision = 20 ticks), avec baisse à ~80/s pendant mes tests concurrents.
- Tableau de bord `ofsi/dashboard.py` (127.0.0.1:8765) : courbes réelles depuis `runs/*/metrics.jsonl`, benchmarks, matériel (GPU « non disponible », températures « non mesurées »). Contrôles pause/reprise/arrêt par fichier, noms validés par regex : testés (traversée de chemin et action inconnue rejetées ; pause/reprise agissent réellement).
- Bug trouvé par test et corrigé : lecture du corps POST invalide qui rejetait aussi les requêtes légitimes.
- `registry/coverage.md` : sur 25 intents → 3 PARTIEL, 1 SCRIPTÉ (spawn), 14 NON couverts, 7 EXCLUS. Aucune maîtrise revendiquée.
- Limites actuelles : spawn et tuile de construction scriptés ; pas de boats/améliorations/diplomatie avancée/armes nucléaires dans l'espace d'actions ; MLP sans mémoire ; aucune évaluation hors entraînement sur seeds retenues ; une seule carte (Onion).

## 2026-11-25 — DIAGNOSTIC : pourquoi 0 victoire (professeur, BC, PPO v1)
Demande utilisateur : vérifier la qualité des 64 000 démonstrations avant de continuer.
- Condition de victoire (code moteur, WinCheckExecution/Config) : posséder > **80 %** des terres non irradiées ; overtime désactivé par défaut ; limite dure 170 min de jeu (102 000 ticks).
- Traces du professeur `conqueror_v1` (3 parties, Onion) : gel du territoire dès t≈4 700 ; troupes 3,0–3,5 M et or 0,3–0,98 M inutilisés ; **82 % des décisions « expand » (1 976/2 412) sans aucun gain de tuile** (plus de terre neutre accessible).
- Analyse des masses terrestres d'Onion (flood-fill moteur) : 12 masses ; 36,4 %, 35,2 %, 13,1 %, 3,4 %… **Aucune masse > 36,4 %**. Les 3 graines ont spawn sur la masse de 74 214 tuiles (35,2 %), d'où le gel identique à 74 214 tuiles.
- CONCLUSION MESURÉE : sans attaque navale (intent `boat`), la victoire est structurellement impossible sur Onion. Le 0 % de PPO v1 (stage 0) et du professeur est un DÉFAUT D'ESPACE D'ACTIONS, pas un échec d'apprentissage.
- Qualité des démonstrations : 64 000 pas, ~90 % étiquetés `expand` (dont ~82 % sans effet) ; la précision d'imitation 99,4 % (validation 98,8 %) est un artefact de labels quasi constants, PAS un indicateur de qualité. Le checkpoint `runs/bc_v1` N'EST PAS retenu comme amorçage de référence.
- Actions décidées : (1) ajouter l'invasion navale à l'espace d'actions ; (2) mesurer les professeurs ; (3) comparer expérimentalement les initialisations (imitation filtrée, aléatoire, auto-supervisée, RL direct) sur un critère mesuré, sans plafonner l'élève à ses professeurs.

## 2026-11-25 — Entraînement suspendu ; audit exhaustif ; environnement v2 (en cours)
- ppo_v1 arrêté proprement (STOP), checkpoint `runs/ppo_v1` conservé mais **marqué invalide** (entraîné dans un espace d'actions qui interdit la victoire). `runs/bc_v1` idem (imitation d'un professeur incapable de gagner).
- Audit automatique (`registry/audit_engine.py` → `registry/engine_audit.json`) : 40 classes d'exécution ; dispatcher = 21 intents (18 de gameplay + emoji, quick_chat, mark_disconnected, toggle_pause). Mécaniques ÉMERGENTES (non commandables, déclenchées par la construction/placement) : trade ships (ports), trains/stations (usines), interception SAM, obus (Defense Post/Warship), explosion nucléaire, croissance des structures. Limite : classification par nom de fichier ; DonateTroops et MIRV mal classés (noms de classes différents).
- `build_unit` est l'action universelle : structures (tuile = emplacement), bombes/MIRV (tuile = CIBLE), Warship (tuile = zone de patrouille). Structures améliorables : City, Port, Factory, SAM, Silo (Defense Post non).
- Nouvelles couches (adapter) : `cands.mts` (candidats d'invasion navale validés par `canBuildTransportShip`, ~160 ms), `state2.mts` (état riche : maxTroops, attaques entrantes/sortantes, unités avec niveau, flags d'interaction exacts par joueur ; candidats build/upgrade/nuke/warship). `step_state` ≈ 20 ms/appel (à optimiser).
- `ofsi/stagnation.py` : détecteur de stagnation mesuré (territorial_stall, troops_idle, gold_hoard, no_land_frontier, blocked).
- `ofsi/teacher2.py` (utilise expansion, conquête, naval, ports/villes/usines/défense, améliorations, silo+bombe, alliance) : **6/6 victoires** sur Onion/Easy/8 bots, 5 022–7 402 ticks (avant : 0 victoire). Confirme que le blocage était l'espace d'actions.
- En cours : test de gagnabilité sur 12 catégories de cartes (benchmarks/teacher2_maps_easy.json).
- À faire (exigé par l'utilisateur) : espace d'actions hiérarchique à pointeurs + masques dynamiques ; encodeurs/têtes neuronaux pour chaque action ; diplomatie/embargo/dons/MIRV/SAM/retraites ; scénarios par compétence ; ré-analyse des 64 000 démonstrations (INUTILISABLES telles quelles : espace v1, étiquettes ~90 % expand sans effet) ; nouvelles démonstrations ; comparaison de 4 initialisations.

## 2026-11-25 — Matériel : GPU réel identifié (mesuré)
- Machine : MSI Prestige 14 AI Studio C1UDXG ; GPU dédié = **NVIDIA GeForce RTX 3050 6 Go Laptop** (PCI VEN_10DE DEV_25AC) — et NON une RTX 3060 comme écrit dans MISSION.txt. Windows le voit avec le statut « Unknown » (éteint : mode graphique intégré / sur batterie). cuInit=100 tant qu'il est éteint. Services NVIDIA actifs.
- À 17:55 : PC sur BATTERIE (21 %), pas sur secteur. L'utilisateur va brancher et activer le GPU (probable redémarrage).
- Plan d'alimentation : unique plan « Utilisation normale » ; ajustements SECTEUR UNIQUEMENT appliqués (CPU min/max 100 %, refroidissement actif, EPP 0). Valeurs d'origine sauvegardées dans docs/power_backup.txt (CPU min 5 % AC/DC, max 100 %). Restauration : `powercfg /setacvalueindex SCHEME_CURRENT SUB_PROCESSOR PROCTHROTTLEMIN 5`.
- Après redémarrage : (1) vérifier cuInit/CUDA ; (2) installer PyTorch CUDA (disque libre ≈ 12 Go : à surveiller) ; (3) MESURER le gain GPU avant toute décision ; (4) relancer le dashboard (127.0.0.1:8765).
- État à reprendre : entraînement SUSPENDU volontairement ; scénarios `ofsi/skills.py` écrits mais NON exécutés ; adaptateur modifié (env.mts overrides) mais pas encore synchronisé (`adapter\sync_adapter.ps1`).

## 2026-11-25 (soir) — GPU opérationnel + 25 scénarios de compétence (mesuré)
- Après redémarrage, secteur branché : **RTX 3050 6 Go** visible (cuInit=0, 1 périphérique, pilote 566.14, CUDA driver 12.7, 54 °C au repos). Disque libre 16,6 Go. PyTorch CUDA (cu126) installé dans `.venv-gpu` (isolé du Python système) — à vérifier/mesurer.
- Les 3 jobs de fond (dont l'évaluation multi-cartes de Teacher2) ont été tués par le redémarrage : À RELANCER.
- Scénarios `ofsi/skills.py` + `ofsi/skills2.py` via `ofsi/run_skills.py` : **25/25 PASS après corrections de TESTS** (jamais du moteur) :
  attack_neutral, attack_player, boat, build×6 (City, Port, Defense Post, Factory, SAM, Silo), upgrade, delete_unit (suppression différée 300 ticks), cancel_attack, alliance (demande/acceptation/prolongation/rupture), alliance_reject, donate, embargo, embargo_all, nuke_atom, nuke_hydrogen (ennemi éliminé 6330→0), nuke_mirv, **sam_intercept** (sans SAM ville détruite 1→0 ; avec SAM 1→1), warship (construction+déplacement), cancel_boat, trade_maritime (ports+navires : tradeGold 5,08 M chacun), trade_trains (usines+villes : trainGold 510 000).
- Faits de jeu appris : rompre une alliance → joueur « traître » ; commerce = levier économique majeur ; la bombe H peut éliminer un joueur ; à 6 300 tuiles un agent peut ne pas avoir de côte.
- Bugs de test corrigés : suppression différée ; élimination de l'ennemi (plus de `self`) ; agent sans accès à la côte ; enregistrement des tests entre modules.
- LIMITES : un test PASS prouve que l'action s'exécute avec l'effet attendu, PAS que l'agent sait l'utiliser. `target_player` : aucun effet observable dans l'état, NON vérifié. `donate` : critère faible (or infini). Scénarios sur Onion uniquement (surcharges or infini/construction instantanée réservées aux tests).

## 2026-11-25 (soir) — Benchmarks GPU (mesuré, RTX 3050 6 Go, sur secteur)
- CPU → GPU (même code PyTorch 2.14.1+cu126), batch inférence 16 / entraînement 256 :
  MLP 256 : inf 0,47→0,12 ms (3,9×), train 5,04→1,39 ms (3,6×) ; MLP 1024 : inf 1,27→0,25 ms (5×), train 20,8→3,37 ms (6,2×) ;
  encodeur d'ensemble à attention (4 couches, 256 d, 56 jetons) : inf 137→5,0 ms (27×), train 2 619→165 ms (15,8×). VRAM pic 1,19 Go.
- Optimisations (attention, train batch 256) : fp32 160 ms ; TF32 140 ms (+14 %) ; **fp16 78 ms et bf16 78 ms (2,05×)**. GPU : 55–57 °C, ≈43 W, 1 695 MHz, util 95–100 %, pas de bridage thermique observé.
- Décisions : entraînement sur GPU en **bf16 autocast + TF32** ; moteurs de jeu sur CPU (16 workers). Conclusion : le GPU est secondaire pour le petit MLP (la simulation domine) mais INDISPENSABLE pour les architectures à entités/attention prévues en v2.
- Profil enregistré : config/hardware.json.

## 2026-11-25 (nuit) — Environnement v2 : gagnabilité, réseau, pipeline (mesuré)
- Teacher2 (v1 d'actions riches) sur 12 catégories de cartes, Easy, 10 bots, 2 parties chacune : **21/24 victoires** (Pangaea, Caucasus, Bosphorus, Danish, Bering, Oceania, Mississippi, BlackSea, Iceland, Africa : 2/2 ; AmazonRiver 1/2 ; ArchipelagoSea 0/2 = plantage du démon pendant l'évaluation à 12 parties parallèles, NON reproduit en partie isolée, cause NON identifiée). Fichier : benchmarks/teacher2_maps_easy.json. Dénominateur de part de terre : mon estimation ≠ celle du moteur (numLandTiles − fallout) → l'observation v2 fournit désormais `win.landTiles` et `win.thresholdTenths` réels.
- Espace d'actions v2 (`ofsi/rl2/space.py`) : 31 types (STOP, ATTACK_NEUTRAL/PLAYER, BOAT, 6 BUILD, UPGRADE, 3 NUKE, BUILD_Warship, MOVE_WARSHIPS, CANCEL_ATTACK/BOAT, DELETE_UNIT, ALLY×4, TARGET, DONATE×2, EMBARGO×4, SPAWN), pointeurs sur une banque de 312 candidats légaux (moteur), paramètre = 5 fractions, ≤3 actions par décision, masques de type/pointeur exacts.
- Réseau v2 (`ofsi/rl2/model.py`) : jetons d'entités + grille géographique conv → transformer (d=128, 4 couches) → décodeur autorégressif ; 1,41 M de paramètres ; pas d'entraînement batch 256 : 203 ms GPU (bf16) vs 2 314 ms CPU. BUG trouvé par test (écart de logp 0,22 entre échantillonnage et réévaluation pour les types sans pointeur) et corrigé → écart 0,00 ; ratios PPO = 1,0.
- Pipeline v2 validé de bout en bout (`ofsi/rl2/test_pipeline.py`, Onion/Easy/8 bots) : **5/6 victoires**, **0 action illégale sur 801 émises**, 133 décisions/s (6 envs, CPU partagé). Le professeur v2 n'utilise que 8 types d'actions sur 31 → ses démonstrations ne couvrent PAS les 23 autres : des professeurs de compétence sont nécessaires (à faire).
- Collecte de démonstrations v2 lancée (`data/demos_v2`, 8 cartes, 4 difficultés, 6/10/14 bots) ; les trajectoires perdantes sont conservées (WorldModel/analyse). Stockage compact float16 + masques empaquetés.
- Hypothèse corrigée : 2 pools de 2 démons ArchipelagoSea tournaient en parallèle (4 processus moteur), job lancé deux fois par erreur de ma part ; sans conséquence sur les résultats mais du CPU gaspillé.

## 2026-11-25 (soir) — Qualité des démonstrations v2 et références mesurées
- Collecte `data/demos_v2` (60 357 décisions, 203 épisodes, 8 cartes × 4 difficultés, 6/10/14 bots, 31 Mo compressés, 1 463 s) : victoires du professeur Easy 53/56 (95 %), Medium 13/52 (25 %), Hard 1/44 (2 %), Impossible 0/51. 67 victoires / 203 épisodes. Issues : Hard 36 morts/44 ; Impossible 45 morts/51.
- COUVERTURE des démonstrations : **12 types d'actions sur 31**. 18 types JAMAIS démontrés : BUILD_SAM, NUKE_Hydrogen, NUKE_MIRV, BUILD_Warship, MOVE_WARSHIPS, CANCEL_ATTACK, CANCEL_BOAT, DELETE_UNIT, ALLY_REJECT/EXTEND/BREAK, TARGET_PLAYER, DONATE_GOLD/TROOPS, EMBARGO_ON/OFF, EMBARGO_ALL_ON/OFF. L'imitation seule ne pourra pas les enseigner → professeurs de compétence ou RL requis.
- Références (eval2.py, 48 parties identiques : 8 cartes d'entraînement + 4 JAMAIS vues × {Easy,Medium} × 2, seeds fixes ; IC de Wilson) :
  * Professeur v2 : Easy 22/24 = 0,92 [0,74 ; 0,98] ; Medium 2/24 = 0,08 [0,02 ; 0,26] ; cartes jamais vues : Easy 7/8, Medium 2/8 (petit échantillon). 13 morts en Medium.
  * Aléatoire légal : 0/48, 47 morts.
- Bug trouvé par l'agent aléatoire et corrigé : `build_obs` plantait sur les unités transitoires (Shell, SAMMissile, MIRVWarhead) absentes de UNIT_T → encodées en vecteur nul (compatible avec les démonstrations existantes).
- Optimisations moteur mesurées (CPU partagé donc bruit) : copie complète des tuiles évitée dans state2 (step_state 19,2 → 13,5 ms) ; candidats de construction regroupés en un seul passage (gain NON mesuré proprement, mesure faussée par la charge).
- Piège : un job lancé via `... | tail` renvoie le code de sortie de tail ; vérifier l'existence des fichiers de résultats.

## 2026-11-25 (soir) — Contrainte mémoire (mesuré)
- Pression mémoire : RAM libre tombée à 4,0 Go sur 31,7 Go ; Claude Code a arrêté 2 jobs d'ATTENTE (pas de calcul perdu). Cause : ~34 processus Node (2 par moteur : tsx + démon ≈ 0,7 Go la paire) = balayage du professeur (8 envs) + évaluation init_bc (8 envs) + préentraînement SSL (3,3 Go) en parallèle. Balayage du professeur ARRÊTÉ (19 processus), RAM libre 6,2 Go ensuite. Variante 1 du balayage (= réglages par défaut) terminée ; variantes 2–4 À REFAIRE séquentiellement.
- RÈGLE DE CAPACITÉ : au plus ~16 moteurs simultanés au total (≈ 11 Go) ; ne pas lancer deux évaluations + un préentraînement en même temps ; OneDrive consomme ~2 Go (hors projet).

## 2026-11-25 (soir) — Recoupement avec la doc d'OpenFront_Agents ; 2 défauts d'observation/action corrigés
Source : `vendor/openfront-agents/docs/AgentMechanics.md` (AGPL ; lue, pas exécutée). OpenFront_Agents est un harnais d'agents pilotés par LLM (Codex) sur une version plus ANCIENNE du moteur (`src/core`) : nécessite compte/API → NON exécutable comme adversaire sous la contrainte « aucun compte externe ». Sa doc sert de source indépendante, croisée avec mes mesures.
- Confirmé par ma mesure : victoire > 80 % des terres non irradiées ; revenu de base ≈ 100 or/tick ; départ 25 000 troupes.
- NOUVEAU (à exploiter) : croissance des troupes `(10 + troupes^0,73/4) × (1 − troupes/max)` culmine vers 42 % de la capacité ; capacité = 2×(tuiles^0,6×1000+50000) + 250 000 par niveau de City ; alliance 5 min, demande 20 s, rupture = « traître » 30 s ; dons : cooldown 10 s.
- **DÉFAUT 1 (observation)** : le moteur renvoie les types de joueur en MAJUSCULES (`BOT`/`NATION`/`HUMAN`) ; mon encodeur cherchait `Bot`/`Nation` → TOUS les joueurs encodés comme bots dans les 60 357 démonstrations et dans ppo2 (bras A : 6 mises à jour). Corrigé (comparaison insensible à la casse). Démonstrations v2 et checkpoints init_bc/init_ssl/init_both INVALIDÉS pour cette raison → collecte, préentraînement et bras PPO à REFAIRE (comparaison arrêtée proprement).
- **DÉFAUT 2 (exclusion injustifiée)** : `emoji` avait été classé « sans effet de jeu ». Le code (NationEmojiBehavior.respondToEmoji) montre : 🖕 → relation −100 avec le destinataire NATION, 🤡 → −10, 🕊️🏳️❤️🥰👏 → +15 en Easy seulement ; tribus/humains : aucun effet. Ajouté comme 32e type d'action `EMOJI` (pointeur joueur, paramètre = {paix, cœur, applaudissements, clown, insulte}), drapeau `canEmoji` exposé.
- **Mesure (skills3)** : les tribus acceptent les demandes d'alliance **5/5** ; nations : Easy 3/3, Medium 3/3, Hard 1/3 (échantillon minuscule). Le professeur n'exploitait pas ce levier → A/B lancé (ally_mode none / threats / all) sur les mêmes 48 parties.
- NT passe de 31 à 32 types ; les anciens fichiers de démonstrations (31 types) ne sont plus compatibles.

## 2026-11-25 (soir) — A/B alliance du professeur (mesuré, mêmes 48 parties, seeds fixes) + pipeline v3 lancé
- Politique d'alliance proactive (`ally_mode`) : Medium base 2/24 (8 %, morts 13) ; `threats` (demander l'alliance aux joueurs ≥ 0,6× mes troupes) 9/24 (38 %, morts 1), McNemar exact +8/−1 p=0,039 ; `all` 8/24 (+6/−0, p=0,031, morts 7). Easy : 22 → 23 (threats), 22 (all). Aucune des deux ne franchit le seuil de Bonferroni (p<0,025 pour 2 comparaisons) : sens et mécanisme cohérents (moins de morts), preuve statistique stricte LIMITÉE (24 parties). `threats` retenu comme professeur par défaut.
- Archivage : checkpoints et démonstrations invalides déplacés dans `runs/_archive_invalides/` et `data/_archive_invalides/` (rien supprimé), avec note explicative.
- Lanceur en un clic `OpenFront-SI.ps1` (doctor/repair/setup/dashboard/train/stop/benchmark/evaluate/skills) : `doctor` testé (voit RTX 3050, CUDA, RAM, disque, SHA-256 des checkpoints). Les autres commandes ne sont PAS encore testées de bout en bout.
- Pipeline v3 séquentiel lancé (`run_pipeline_v3.sh`, journal `pipeline_v3.log`) : skills_full → collecte (60 000 décisions, ally_mode=threats) → préentraînement bc/ssl/both (2 400 pas) → 4 bras PPO (120 000 décisions chacun) + évaluation. Durée estimée 4 à 5 h.

## 2026-11-25 (soir) — DECISION OUVERTE (utilisateur) : évaluer openfront-ai ?
- openfront-ai (djmango) : AUCUNE licence (droits réservés) ; épingle un AUTRE commit du moteur (58c536b7 ≠ db8bf7c4 de ce projet) avec 5 correctifs ; exige Python ≥ 3.12 (ici 3.11), poids Hugging Face (djmango/openfront-rl, safetensors), autoencodeurs figés, chaîne Rust/TypeScript propre. Conditions NON comparables sans exécuter SON moteur. Option A : ne pas l'exécuter (statu quo, aucune revendication de comparaison). Option B : l'exécuter localement et en privé sur son moteur épinglé pour une mesure de référence (zone grise de licence : usage privé sans redistribution, aucun code copié). Décision à prendre par l'utilisateur ; non exécuté en l'état.
- OpenFront_Agents : harnais LLM (Codex) → compte/API requis → NON exécutable sous la contrainte « aucun compte externe ». Sa doc de mécaniques a servi de source de recoupement (2 défauts trouvés).

## 2026-11-25 (soir) — Preuves de competence completes + defauts de test corriges
- `benchmarks/skills_full.json` : **30/30 scenarios PASS** (execution complete en 46 s CPU libre). Matrice de preuves `registry/coverage_v2.md` (generee) : **19 intents de gameplay sur 19 valides par scenario** a effet verifie, 0 sans scenario. PASS = l'action s'execute avec l'effet attendu ; NE PROUVE PAS que l'agent la maitrise.
- Defauts de TEST trouves et corriges (jamais du moteur) : intents `emoji` sans `clientID` (ignores en NoOp) ; alias de noms entre matrice et tests ; suppression d'unite differee de 300 ticks.
- Effets mesures : emoji 🖕 → relation de la nation envers moi Neutre(2) → Hostile(0) ; `targetPlayer` → cible dans `targets()` et relation 2 → 1 (−40) ; tribus 5/5 alliances ; SAM sauve la ville (1→1 vs 1→0) ; MIRV et bombe H detruisent (H : ennemi elimine) ; commerce maritime 5,08 M d'or et trains 510 000.
- `state2` expose maintenant `theirRelation` (DIAGNOSTIC uniquement, non fourni a l'agent : information interne des nations) et `targets`.
- Professeur v3 (`teacher_v3.py`) : regles sensees pour SAM, warships, bombe H/MIRV, annulation d'attaque, embargo, extension/rupture d'alliance, ciblage, emoji, dons. EN COURS de validation A/B (memes 48 parties) contre v2+alliance : aucune demonstration v3 n'est utilisee avant cette mesure.

## 2026-11-25 (soir) — Demonstrations v3, professeur v3 (resultat NEGATIF), ligue, garde-fou memoire
- Collecte `data/demos_v3` (observations corrigees, 32 types, professeur v2+alliance `threats`) : 60 056 decisions, 148 episodes, 59 victoires, 34 Mo, 1 236 s. Victoires du professeur : Easy 40/42 (95 %), Medium 17/37 (46 %), Hard 2/33 (6 %), Impossible 0/36. Couverture : **12/31 types demontres, 19 jamais** (SAM, bombes H/MIRV, warship, annulations, suppression, rejet/extension/rupture d'alliance, ciblage, dons, embargos, EMOJI). Compte par type : `registry/demo_type_counts.json`.
- **RESULTAT NEGATIF — professeur v3** (22 types d'actions, regles « sensees ») sur les 48 parties de reference : Medium 6/24 contre 9/24 pour v2+alliance (McNemar p=0,51, non significatif) mais **morts 12 contre 1** ; cartes jamais vues Medium 0/8 contre 3/8. Une ou plusieurs de mes regles sont nuisibles (soupcons : ALLY_BREAK 160 usages, TARGET_PLAYER 380 usages). Ablation par regle lancee (4 variantes Medium, memes seeds). AUCUNE demonstration v3 n'est utilisee avant ces resultats.
- Ligue (code, NON executee en conditions reelles) : `env2_multi.py` (k agents dans le meme moteur, via proxy), `league.py` (agents heterogenes, Bradley-Terry + IC bootstrap, matrice de confrontations, regle de promotion). Test unitaire de la regle de promotion : un BUG detecte (mauvaise queue binomiale : un candidat regressant de 9 pertes/1 gain etait promu) corrige ; 5 cas verifies.
- Garde-fou memoire (`memguard.py`) : ppo2 et eval2 attendent d'avoir (0,8 x moteurs + 4,5 / 3,0) Go libres avant de demarrer leurs moteurs.

## 2026-11-25 (soir) — Ablation du professeur v3 (memes 24 parties Medium) et surapprentissage SSL
- Medium, victoires/morts : v2+alliance 9/24 (1 mort) ; v3 COMPLET 6/24 (12) ; v3 sans {break,target} **15/24 (1 mort, progression 0,69)** ; v3 sans break seul (garde target) 5/24 (9 morts). => `TARGET_PLAYER` est la regle nuisible (chaque ciblage fait chuter de 40 la relation de la cible envers moi ; 380 usages) ; `ALLY_BREAK` non confirmee comme fautive (variante « tout sauf target » a lancer). McNemar de no_break_target vs v2 : +9/−3, p=0,146 (NON significatif seul).
- SSL : perte de prediction de victoire 0,017 (train) contre 2,3–2,5 (validation par episode ; hasard 0,64) = SURAPPRENTISSAGE (memorisation d'episodes, 148 episodes seulement). Correction : le checkpoint retenu est celui de MEILLEURE validation, applique aux 3 methodes (equite). Pipeline v3 arrete et relance (v3b).
- Ligue : premiere execution reelle multi-agents (random vs teacher2, sieges echanges) : OK. Defauts trouves : Bradley-Terry diverge a 100 % de victoires (a priori faible ajoute) ; l'agent aleatoire ne spawnait pas toujours (corrige dans league.py et eval2.py ; la baseline aleatoire 0/48 reste valide car 0 victoire quoi qu'il arrive).

## 2026-11-25 (soir) — Lanceur : tests reels
- `OpenFront-SI.ps1` : `doctor`, `repair`, `dashboard` testes (le tableau de bord n'est pas lance en double ; l'API repond ; les dossiers d'archive `_*` ne sont plus listes comme runs). `stop` et `train` : NON testes de bout en bout (stop n'agit que sur des runs ayant un metrics.jsonl ; train lancerait un entrainement). `setup`, `benchmark`, `evaluate`, `skills` : NON testes via le lanceur.
- LIMITE CONNUE : le lanceur ne rend pas la main si sa sortie est branchee sur un tube (`... | tail`) car le processus cache du tableau de bord herite du handle du tube ; usage normal en console/double-clic non concerne. A corriger en detachant explicitement les handles.
- Calibration memoire (mesuree) : 18 processus Node = 3,3 Go (~0,2 Go chacun, ~0,4 Go par moteur) — mon estimation precedente (0,7 Go/paire) etait trop pessimiste et aurait fait attendre indefiniment le garde-fou. Gros consommateurs hors projet : Brave ~5,4 Go, OneDrive ~2,2 Go, ChatGPT ~1,5 Go (non touches). Garde-fous recalibres : PPO 0,45 x envs + 3,5 Go ; eval 0,45 x envs + 2,0 Go.
- Correction : plusieurs titres de ce journal portaient la date 2026-11-26 par erreur ; l'horloge systeme indique le 2026-11-25 (soir). Corrige.

## 2026-11-25 (soir) — PLAFOND DE FREQUENCE CPU (mesure, probablement mode MSI) + arret des ablations secondaires
- Constat : le moteur est devenu ~10x plus lent vers 21h06 (step_state 13,5 ms -> 157 ms ; cands 9 -> 142 ms ; reset 1,1 -> 4,9 s ; 3,8 decisions/s pour UNE session). Cause mesuree : plafond de frequence CPU a **1 400 MHz** (nominal 3 800 MHz ; cœurs a 700-900 MHz), temperature NORMALE (zone thermique 50 °C, GPU 40 °C, aucun bridage thermique GPU), secteur branche, batterie 100 %. Processus `MSI_AmbientSilent` + services MSI Center actifs : plafond logiciel probable du mode constructeur (silencieux/economie). Non modifiable par l'agent (reglage utilisateur, hors droits).
- Effet : apres arret de mes ablations secondaires (safe_only, none, no_target — a REPRENDRE plus tard), debit remonte a 17,8 decisions/s (step_state 33,6 ms) : environ 2x plus lent que la reference d'il y a quelques heures.
- ACTION UTILISATEUR RECOMMANDEE : MSI Center -> scenario « Extreme Performance » et desactiver « Ambient Silent » ; gain attendu 2-3x sur les moteurs (non garanti).
- Lanceur : `doctor` signale desormais la frequence CPU et avertit si < 60 % du nominal (teste : affiche 30 % ici).
- Pipeline reordonne (v3c) : bras PPO dans l'ordre B_bc, D_both, C_ssl, A_random (du plus au moins informatif) car le CPU plafonne (~8 h estimees pour les 4 bras) ; A_random (poids aleatoires) n'avait aucune chance de victoire en 120 000 decisions dans l'essai v1.
- SSL : surapprentissage confirme (val_wm_win 2,3 vs train 0,013) ; la selection par meilleure validation retient une epoque tres precoce => l'initialisation SSL est presque un reseau non entraine. Resultat de la METHODE, rapporte tel quel.
- Resultat contrefactuel preliminaire : la meme configuration (carte, bots, graine du jeu) a donne une victoire avec une graine de professeur differente alors que la reference avait perdu : le resultat d'une partie est CHAOTIQUEMENT sensible a de petits choix ; les petits echantillons (24 parties) sont donc fragiles.
- Documentation : README.md (utilisateur, etat honnete) et docs/DEVELOPER.md (architecture, invariants, regles de methode).

## 2026-11-25 (soir) — Premiere analyse contrefactuelle d'une DEFAITE (mesure, 1 partie)
- Partie : BosphorusStraits, 12 bots, Medium, graine e01000015 ; professeur de base (sans alliance, sans regles v3). Graine de professeur 1 = victoire (468 decisions) ; graine 2 = MORT apres 339 decisions. Rejeu de la defaite : durée identique (339) => determinisme confirme (`benchmarks/counterfactual_defaite.json`).
- 9 snapshots exacts dans les 200 dernieres decisions, 8 alternatives legales chacun, horizon 50 decisions. A la decision 299 (tick 6162, menace entrante 18 073) : suite normale => MORT (progression 0,00) ; **« demande d'alliance au joueur le plus fort » => SURVIE (+0,08)**. Aux instants anterieurs : ecarts <= +0,04 (defaite tardive, diplomatie/defense, pas expansion).
- Coherent avec l'A/B alliance (morts 13 -> 1), MAIS : UNE seule partie, UN instant decisif, suite jouee par un professeur neuf (pas la trajectoire d'origine), horizon fini. A traiter comme indice ; generaliser exigerait des dizaines de defaites analysees.
- Defaut de lancement corrige : `read` sans saut de ligne final renvoie 1 et court-circuite `&&` => faux succes affiche ; toujours verifier l'existence du processus apres un lancement en arriere-plan.
- Defaut du pipeline v3c : condition d'attente `ckpt -ot log` jamais vraie (le journal est ecrit apres le checkpoint) => le pipeline attendait indefiniment ; ~15 min de calcul perdues. Corrige (attente de la ligne `checkpoint:` du journal). SSL : meilleure validation a l'epoque 1 seulement (val_total 1,669 ; derniere epoque 12) => init SSL quasi non entrainee. BC : epoque 20 (val_total 0,650).
- Selection d'epoque : `both` a retenu l'epoque 0 (val_total 2,598 dominee par la tete « victoire » qui surapprend) => init defectueuse (homme de paille). Corrige : `--select bc|dyn` (la selection suit ce que chaque methode optimise) et `--wm-win-weight 0.1`. Orchestrateur v3d : bras B (init BC, PPO deja lance a 11,5 decisions/s car CPU plafonne) ; puis evaluation de B EN PARALLELE du re-preentrainement (ssl select=dyn, both select=bc) ; puis D, C, A avec les initialisations corrigees (`init_ssl_v2`, `init_both_v2`). Les initialisations `init_ssl`/`init_both` d'origine ne sont PAS utilisees pour PPO.
- Piege recurrent : un `Stop-Process` filtre sur du texte present dans ma propre commande tue le shell de l'outil (code 255) ; toujours exclure `$PID` / verifier l'etat reel avant de relancer.

## 2026-11-25 (soir) — PPO depuis une imitation : derive de la politique (mesure) et recette corrigee
- Bras B (init BC) recette v1 (lr 2,5e-4, entropie 0,01, critique non entraine) : des la 1re mise a jour **KL 0,94 et 52 % d'echantillons ecretes** ; entropie 0,76 -> 1,57 en 6 mises a jour (la politique imitee se degrade). Premiers episodes pourtant gagnes (3/3 Easy). Archive : `runs/_archive_invalides/arm_B_bc_recette_v1_derive`.
- Recette v2 (identique pour TOUTES les initialisations pre-entrainees) : `--value-warmup 8` (seule la tete de valeur est mise a jour, verifie : 4 parametres modifies, tous `value.*`), lr 1e-4, entropie 0,005. Initialisation aleatoire : 0 echauffement.
- Orchestrateur v3e : B_bc -> [eval B || re-preentrainement ssl(dyn)/both(bc)] -> D_both -> C_ssl -> A_random.
- Recette v2 VALIDEE sur le bras B (12 mises a jour) : pendant l'echauffement KL = 0,0 et ecretage 0 % (politique gelee) ; apres : KL 0,015-0,12, ecretage 8-24 % (contre 0,94 / 52 % en v1) ; entropie stable ~0,9-1,1 (contre 1,57) ; 10/10 episodes Easy gagnes. Debit 11 decisions/s (CPU plafonne) => ~3 h pour 120 000 decisions. `OpenFront-SI.ps1 train [nom] [ckpt]` utilise desormais cette recette (syntaxe verifiee, NON execute).
- Lanceur : la commande `train` utilise la recette validee (lr 1e-4, entropie 0,005, echauffement 8 si checkpoint fourni). Deux defauts de MA fabrication trouves en la modifiant : (1) un `\r` ecrit dans une chaine est devenu un CARACTERE retour-chariot dans le chemin (`ofsi<CR>l2\ppo2.py`) ; (2) ma 1re verification « syntaxe OK » etait mal ecrite et ne prouvait rien. Corriges ; syntaxe PowerShell verifiee avec le parseur (0 erreur). La commande `train` reste NON executee de bout en bout.

## 2026-11-25 (nuit) — Demande utilisateur : audit de performance apres l'experience en cours
- Instruction : apres la fin de l'experience, audit complet du debit (~14 dec/s juge faible), SANS supposer que le CPU est le goulot ; tester 1..32 workers, protocoles binaires/memoire partagee/envs vectorises/asynchrone/caches incrementaux/Rust-C++-CUDA si justifie ; viser 100 puis 500/1000 dec/s ; ne jamais degrader fidelite/observations/actions/reseau ni gonfler les decisions ; autotuner ; preserver les checkpoints ; ne pas fausser l'experience en cours.
- Plan : `docs/PERF_AUDIT_PLAN.md` (declenche a « PIPELINE TERMINE »). Aucun fichier de l'experience n'est modifie d'ici la.
- Constats PASSIFS (bras B, 91 MAJ) : collecte 96,7 % du temps, entrainement GPU 3,3 % (1,9 s/MAJ) ; pas de collecte synchronise de 8 moteurs ~874 ms vs 26-60 ms pour un moteur seul ; debit 2,5-30 dec/s, 15-30 apres que Brave passe de 37 a 19 processus (hypothese de contention a CONFIRMER par mesure, pas une conclusion).
- Correction utilisateur-materiel : le GPU est une RTX 3050 6 Go (verifie), pas une 3060.

## 2026-11-26 (matin) — FIN DE L'EXPERIENCE DES 4 INITIALISATIONS : resultats et 3 defauts majeurs
Chronologie : PPO du bras B termine a 00:49 ; ma question a l'utilisateur (AskUserQuestion) est restee sans reponse pendant des heures, l'orchestrateur a donc continue par defaut ; `PIPELINE TERMINE` a 05:27. L'utilisateur a repondu ensuite « arreter apres B, puis audit » : sans objet pour l'entrainement (deja termine), valide pour la suite (audit).
**Resultats mesures (48 parties de reference, seeds fixes)** :
- Bras B (init imitation filtree + PPO recette v2, 120 320 decisions) : Easy **7/24** (IC95 0,15-0,49), Medium **2/24** — tres inferieur a son professeur (Easy 23/24, Medium 9/24). Victoires Medium en entrainement par blocs de ~20 episodes : **14, 7, 3, 4, 3** => DEGRADATION reelle de la politique par PPO.
- Test de l'hypothese « le greedy emet STOP » (sur 600 observations de demonstrations) : REFUTEE. init_bc : STOP en 1er slot 62,5 % (greedy) / 46,8 % (echantillonne) ; B apres PPO : 26,3 % / 28,3 % (agit PLUS) ; accord de type avec le professeur 56,3 % -> 34,2 %. La degradation n'est pas un artefact de decodage.
- Bras D (both), C (ssl), A (aleatoire) : **PLANTES** (D a 79 360/120 000 decisions, C a 30 720, A a 19 456) ; leurs evaluations (C 0/24, A 0/24, D absente) ne sont PAS des resultats de methode. NE PAS les comparer.
**DEFAUT 1 (adaptateur, robustesse)** : `AllianceExtensionExecution.ts:28` fait `console.info("[AllianceExtensionExecution] Player ... is not alive")` => ecrit sur STDOUT (mon canal de protocole) ; ma redirection ne couvrait que `console.log` ; `[` ouvre un tableau JSON puis le texte casse : `JSONDecodeError ... column 2 (char 1)`. Les bras D/C/A (plus exploratoires, ils emettent ALLY_EXTEND) ont plante ; B (imitation, jamais ALLY_EXTEND) non. CORRIGE : demon redirige TOUTES les methodes console + `process.stdout.write` vers stderr (protocole via PROTO_WRITE) ; client ignore toute ligne non-JSON (`noise_lines`). Test de regression (`selftest_noise`, faux demon) : PASS ; 30/30 scenarios PASS apres correctif.
**DEFAUT 2 (recette PPO)** : la recette v2 (echauffement valeur, lr 1e-4, entropie 0,005, sans ancrage) degrade la politique imitee. A remplacer (ancrage KL sur la politique initiale / perte d'imitation auxiliaire, lr plus bas) avant de refaire la comparaison.
**DEFAUT 3 (methode)** : j'ai pose une question bloquante a l'utilisateur pendant que le calcul continuait ; la reponse est arrivee apres la fin. A eviter : prendre la decision par defaut documentee ou ne pas bloquer.
- Debits (meme experience) : B ~7-30 dec/s (contention + plafond CPU) ; D/C/A 43-58 dec/s (machine plus calme) => la contention avec d'autres applications explique au moins la moitie de la variabilite.
- Checkpoints conserves : runs/arm_{B_bc,D_both,C_ssl,A_random} (D/C/A partiels).

## 2026-11-26 (journée) — Portage Linux (conteneur cloud 4 cœurs, sans GPU) et PPO ancré (protocole fixé AVANT les résultats)
- Environnement : le dépôt a été repris dans un conteneur Linux (4 cœurs, 15 Go, PAS de GPU, Node 24.22.3 / npm 12.2.3 installés en local dans `tools/node24` via le paquet npm `node@24`, torch 2.15.0+cpu dans `.venv`). Moteur reconstruit au commit épinglé `db8bf7c4` (`vendor/`, ignoré par git).
- Portabilité corrigée (2 défauts de MA fabrication, Windows seulement) : chemin `node.exe` en dur dans `ofsi/client.py` ; `ctypes.windll` dans `memguard.py` (remplacé par `/proc/meminfo` sous Linux). Aucun changement du protocole ni du moteur.
- **Reproduction indépendante (mesurée)** : `snapshot/restore` à hash identique (`9862040910910476`) ; **30/30 scénarios PASS** (`benchmarks/skills_linux.json`) avec les MÊMES valeurs que sous Windows (commerce maritime 5 083 868 or, trains 510 000, bombe H 6 330 → 0 tuiles) ; pipeline v2 (Onion/Easy/8 bots, 8 parties) : 7/8 victoires, 0 action illégale sur 1 070, **147,5 décisions/s** (CPU libre, professeur scripté).
- PPO ancré (défaut 2 du 2026-11-26 matin) : `ppo2.py` gagne `--kl-ref` (pénalité k3 de KL(π‖π_init), π_init gelée) et `--bc-coef` (log-vraisemblance auxiliaire sur les décisions GAGNANTES du split train de `demos_v3`). Désactivés par défaut : les anciennes expériences restent reproductibles.
- PROTOCOLE (fixé avant résultat) : bras `arm_B_anchor` = init `runs/init_bc` ; `--lr 3e-5 --ent 0.005 --value-warmup 8 --kl-ref 1.0 --bc-coef 0.5` ; 6 moteurs, T=64, 60 000 décisions (la moitié du budget du bras B d'origine), seed 0. Évaluation : `eval2.py`, mêmes 48 parties (seeds fixes), greedy. RÉFÉRENCES déjà mesurées : init_bc seul Easy 19/24, Medium 3/24 ; bras B v2 Easy 7/24, Medium 2/24 ; professeur Easy 23/24, Medium 9/24. CRITÈRES : l'ancrage « fonctionne » seulement si Easy ≥ init_bc (19/24) SANS dégradation Medium ; une amélioration au-delà de init_bc n'est revendiquée que si McNemar apparié p<0,05. Limites connues d'avance : CPU/torch CPU ≠ CUDA (non bit-identique au bras B), 1 seule graine, 48 parties.

## 2026-11-26 (journée) — Notifications §45 et modèle des adversaires §24 (mesurés)
- `ofsi/notify.py` (+ `test_notify.py`, 15/15 PASS sur données synthétiques) : plateau, régression, record de débit, divergence, disque ; bannière §45 (`/api/status`) qui n'affiche « IA LOCALE VALIDÉE » QUE si `docs/validation.json` contient `all_pass:true` (cas fichier absent/corrompu/false testés). Testé sur les vrais runs : détecte un vrai plateau d'`arm_C_ssl` (taux de victoire figé à 0,01, run planté, cf. entrée du matin).
- `docs/PROOF_MATRIX.md` créé : 46 sections, statuts honnêtes. Lacunes SANS CODE au départ : §24 adversaires, §25 planification, §33 évolution, §34 autotune, §35 ordonnanceur (partiel), §43 orchestrateur. Bannière actuelle : VALIDATION PARTIELLE.
- **Modèle des adversaires** (`ofsi/rl2/oppmodel.py`, `test_oppmodel.py` 7/7 PASS) — par adversaire, à h=5 et 20 décisions : Δ log-tuiles, Δ log-troupes, Δ part de terre ; événements élimination / devient allié / devient traître. Split PAR ÉPISODE (119 train / 29 val, 86 757 lignes de validation), 36 s sur CPU, 1 thread.
  * DÉFAUT trouvé avant d'entraîner : `state2` ne garde que les joueurs VIVANTS (`isAlive()`), donc la liste se COMPACTE à chaque élimination et un emplacement ne désigne plus le même joueur → cibles fausses. Corrigé par reconstruction d'identités (alignement DP en sous-séquence) ; testé sur données synthétiques à vérité connue.
  * Résultats (`benchmarks/oppmodel.json`) : gain d'erreur vs persistance (delta 0) : tuiles h=20 **+42 %**, troupes h=20 +27 %, part de terre h=20 +22 % ; AUC : élimination 0,95/0,92 (h5/h20), devient allié 0,91/0,90, devient traître 0,83/0,81.
  * Ablation historique : l'historique (t-1, t-5) n'ajoute que +0,00 à +0,04 de gain et ~0 d'AUC → la prédiction vient surtout de l'état courant.
  * SOUPÇON de fuite testé et RÉFUTÉ : retirer les drapeaux d'interaction (incomingRequest, canAlly, etc.) ne change pas les AUC (0,906 → 0,906 ; `benchmarks/oppmodel_nodiplo.json`).
  * LIMITES : toutes les démonstrations viennent du MÊME professeur (distribution étroite : le modèle prédit des adversaires face à CE professeur, pas face à n'importe quel agent) ; le modèle n'est PAS encore branché sur la politique (donc aucun gain de jeu démontré) ; 1 graine.

## 2026-11-26 (journée) — Planificateur par recherche sur snapshots (§25) : protocole fixé AVANT résultats
- Code : `ofsi/rl2/planner.py` (recherche : snapshot → action du professeur + 7 alternatives légales → simulation de H=30 décisions avec un professeur de rollout → score = progression (victoire +3, mort −1) ; on ne quitte l'action du professeur que si le gain > marge 0,05, contre la malédiction du vainqueur ; planification 1 pas sur 4), `eval_planner.py` (évaluation APPARIÉE : mêmes 24 parties Medium, même graine de professeur par partie, même code d'exécution pour les 2 bras), `test_planner.py` (2/2 PASS).
- Test de correction : l'état du moteur après la recherche est identique à celui d'avant (tick + tuiles/troupes/or/vivant de tous les joueurs) ; avec marge infinie la partie est bit-identique à la partie sans planification (hash final). Défaut de MON test trouvé en route : j'avais comparé le champ `hash` du démon, qui est un CACHE (dernière valeur calculée, remis à `None` par une restauration) et pas l'état du jeu ; corrigé, hash final conservé comme preuve.
- PROTOCOLE : 4 bras sur les 24 mêmes parties Medium (seed0 1 000 000, bots 8/12) : (1) professeur `threats`, (2) professeur `threats`+planificateur, (3) professeur `none`, (4) professeur `none`+planificateur. Critère : le planificateur « améliore » seulement si victoires(planificateur) > victoires(professeur seul) avec McNemar exact apparié p<0,05 ; sinon résultat rapporté comme non significatif. Références non appariées déjà mesurées (graines de professeur différentes) : threats 9/24, none 2/24.
- Limites connues d'avance : le professeur de rollout est le même que celui qui joue (la recherche suppose que l'avenir est joué par lui) ; horizon 30 décisions ≪ durée d'une partie (~400) ; 24 parties ; sensibilité chaotique des parties (cf. contrefactuel).
