# Plan d'audit de performance (demande utilisateur du 2026-11-25 soir)

**Declenchement** : UNIQUEMENT quand `pipeline_v3.log` affiche `PIPELINE TERMINE` (comparaison des 4 initialisations terminee et evaluee). D'ici la :
* aucun fichier utilise par l'experience n'est modifie : `ofsi/rl2/{ppo2,eval2,pretrain,space,env2,vecenv2,model,teacher_v2,teacher_v3,ckpt,memguard}.py`, `adapter/*`, `ofsi/client.py` ;
* aucun profilage ni benchmark ne tourne (ils fausseraient les mesures de debit de l'experience) ;
* le code d'audit est ecrit dans de NOUVEAUX fichiers (`perf/`), jamais importes par le pipeline en cours.

**Contraintes de l'utilisateur** (a respecter strictement) : ne pas degrader la fidelite du moteur, la richesse des observations, la couverture des actions, la complexite neuronale ni la qualite strategique ;
ne pas gonfler le nombre de decisions ni changer leur frequence (`decide_every = 20` ticks reste fixe) ; comparer chaque optimisation a la reference precedente avec tests de fidelite et de non-regression ;
preserver les checkpoints ; ne pas supposer que le CPU est le facteur limitant.

## 0. Faits deja mesures (passifs, sans perturber l'experience)

| fait | mesure |
|---|---|
| part de la collecte dans une mise a jour PPO | **96,7 %** (entrainement GPU : 3,3 %, 1,9 s / MAJ) — le GPU n'est PAS le goulot |
| temps de collecte d'un pas synchronise de 8 moteurs | ~874 ms en moyenne (vs 26-60 ms pour un moteur seul) : cout dominant = file/synchronisation/contention, pas le calcul du jeu |
| debit | 2,5 a 30 dec/s ; 7-11 sous forte contention, 15-30 apres la baisse de charge d'autres applications (Brave 37 -> 19 processus) |
| plafond de frequence CPU | 1 154 MHz moyen / 3 800 MHz nominal (mode MSI probable) ; temperature 50 °C (pas de bridage thermique) |
| materiel | Core Ultra 7 155H 6P+8E+2LPE (22 threads), RTX **3050** 6 Go (et non 3060), 31,7 Go RAM |

## 1. Instrumentation (A) — d'abord MESURER

1. `perf/sysmon.py` : echantillonnage 1 Hz par coeur logique (charge, frequence, classe d'efficacite P/E/LPE), GPU (`nvidia-smi` : util, horloges, puissance, temperature, memoire), RAM, CPU par processus (node/python). CSV horodate.
2. Variante profilee du demon (`adapter/daemon_prof.mts`, copie instrumentee) : decoupage par commande en : simulation des ticks / construction d'etat (`state2`) / generation de candidats (par type) / serialisation JSON / ecriture stdout.
3. Profil V8 (`--cpu-prof`) d'un moteur sur une partie representative -> fonctions chaudes.
4. Profil Python (cProfile + chronometres) du pas `VecEnv2._one` : IPC (ecriture/lecture), `json.loads`, `build_obs`, `collate`, inference, GIL.
5. Microbenchmarks isoles : cout JSON (taille et temps) de `state2`, des candidats, de `grid2` ; cout `build_obs` ; latence aller-retour IPC a vide (commande `ping`).
6. GC Node : `--trace-gc`, frequence/duree des pauses ; pression memoire.

## 2. Parallelisme (B) — mesurer, ne pas supposer

* Matrice N moteurs in {1, 2, 4, 6, 8, 12, 16, 22, 32} x affinite {tous coeurs, P seulement, E seulement, P+E sans LPE} x garde-fou RAM, charge SOUTENUE (>= 5 min apres echauffement), politique scriptee (sans GPU) PUIS politique neuronale (avec GPU).
* Mesures : decisions/s, ticks/s, parties terminees/h, latence p50/p95/p99 d'un pas, CPU/GPU/RAM/VRAM, frequence par classe de coeur, temperature, ecart au plus lent (synchronisation).
* Etat des lieux de la synchronisation : un pas PPO attend le moteur le plus lent (`pool.map`). Tester : rollouts ASYNCHRONES (chaque moteur avance a son rythme, tampon par moteur), puis lots decouples inference/simulation.

## 3. Pistes architecturales (C) — evaluees par benchmark avant toute adoption

1. **Un seul processus Node hebergeant N moteurs en `worker_threads`** (au lieu de 2 processus par moteur) : cartes statiques partagees, moins de memoire/demarrage.
2. **Construction des observations cote Node** (tenseurs numeriques plats) au lieu de JSON -> dict -> numpy : evite l'analyse JSON et les boucles Python sous GIL.
3. **Protocole binaire** (MessagePack ou format maison tableaux types) et/ou memoire partagee (SharedArrayBuffer / fichier mappe) pour les observations ; comparer a JSON mesure.
4. **Caches incrementaux** : candidats navals (statiques par masse terrestre, invalides seulement si territoire change), tuiles de construction (invalidation par evenement), drapeaux d'interaction joueurs (recalcul par joueur modifie), grille geographique (delta).
5. **Calculs redondants** : `state2` appelle `playerActions` par joueur ; `buildCandsAll` copie `[...me.tiles()]` ; `grid2` echantillonne 1/2 de la carte ; mesurer et reduire SANS changer les valeurs.
6. **Inference** : batching deja par pas ; tester pipeline GPU double-tampon (inference du pas t+1 pendant la simulation de t), `torch.compile`/CUDA graphs si Triton disponible sous Windows, bf16 deja en place.
7. **Portage Rust/C++/CUDA** : uniquement des portions DONT le profil montre qu'elles dominent ET dont l'equivalence exacte est testable (candidats, observation). Le moteur de jeu officiel n'est PAS reecrit (fidelite).

## 4. Fidelite et non-regression (D) — a chaque optimisation

* Meme graine + memes actions => meme `hash` final du moteur (reference = moteur officiel inchange) ; snapshot/restore identiques.
* Egalite EXACTE (ou a 1e-6 pres pour les flottants) des tenseurs d'observation, masques de type et de pointeur, avant/apres, sur des centaines d'etats de cartes/difficultes varies.
* `ofsi/run_skills.py` : 30/30 PASS ; `test_pipeline.py` : 0 action illegale ; evaluation de reference : memes victoires pour le professeur (determinisme).
* Aucune modification de `decide_every`, du nombre/typage des actions, de la richesse des observations.

## 5. Systeme d'auto-optimisation (E)

`ofsi/autotune.py` : au premier lancement et quand carte/modele/materiel changent (empreinte : CPU, GPU, RAM, taille de carte, hash du reseau), balayage court de N moteurs / affinite / taille de lot, selection du meilleur debit SOUTENU sous contrainte RAM/VRAM/temperature, ecriture de `config/autotune.json`, relecture par `OpenFront-SI.ps1 train`. Re-mesure periodique en cours d'entrainement (derive de debit) avec ajustement a chaud des workers.

## 6. Metriques de sortie (F)

Pour chaque configuration : decisions/s, ticks/s, parties/h, latences p50/p95/p99, utilisation CPU/GPU/RAM/VRAM, frequences, temperatures ; et **progression d'intelligence par heure** = amelioration mesuree du taux de victoire (batterie de reference, memes parties) et de la progression vers le seuil de victoire par heure de mur, a decisions egales (l'efficacite d'echantillonnage ne doit pas changer : seul le temps par decision baisse). Objectifs initiaux : 100, puis 500, puis 1 000 decisions/s ; **non consideres comme des plafonds**.

## Annexe — topologie CPU REELLE (lue via GetLogicalProcessorInformationEx, `perf/topology.json`)
* Classe d'efficacite 1 : **6 P-cores avec SMT** = 12 threads logiques `{0,1,10..19}`, masque d'affinite `0xFFC03`.
* Classe d'efficacite 0 : **10 coeurs sans SMT** = 8 E-cores `{2..9}` + 2 LP E-cores `{20,21}`, masque `0x3003FC` (Windows ne les distingue pas ici).
* Frequences observees sous le plafond actuel : P-cores ~1 400 MHz, E-cores ~900 MHz, LP E-cores ~700 MHz => le plafond touche TOUTES les classes (pas seulement un mauvais placement).
* Matrice d'affinite a tester : tous (0x3FFFFF) | P seulement (0xFFC03) | P sans SMT (un thread par coeur) | E seulement (0x3003FC) | P+E sans LP-E (0x3FFFFF & ~0x300000).
