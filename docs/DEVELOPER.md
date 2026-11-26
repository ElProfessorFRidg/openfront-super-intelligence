# Documentation developpeur

## Architecture

```
Python (ofsi/)  <--JSON-lines stdin/stdout-->  Node daemon (adapter/daemon.mts)  --appelle-->  moteur officiel (GameRunner, deterministe)
```

* **Un moteur = un processus** (2 processus Node avec `tsx`, ~0,4 Go mesure). `ofsi/client.py:OFEnvProc` : `reset`, `step_state`, `state2`, `cands`, `grid2`, `snapshot`, `restore`, `landmasses`.
* `adapter/run_ts.ps1` / `sync_adapter.ps1` copient `adapter/` dans `vendor/openfront-engine/osi/` (les jonctions Windows cassent la resolution des paquets `@openfront/*`). **Ne jamais synchroniser pendant qu'un moteur demarre.**
* Les intents sont `StampedIntent` (avec `clientID`) ; **un intent sans `clientID` est ignore (NoOp)** — piege deja rencontre.
* `stdout` est reserve au protocole : le demon redirige `console.log` vers `stderr`.

## Espace d'actions v2 (`ofsi/rl2/space.py`)

32 types (`TYPES`), chacun : (type) -> pointeur dans une banque de **312 candidats** a offsets fixes (`DOM`/`OFF`) -> parametre (5 fractions ; pour `EMOJI` : 5 emojis a effet de jeu). Jusqu'a `M_SUB=3` actions par decision,
doublons de type interdits. Les **masques** (`type_mask [NT]`, `ptr_mask [NT,NB]`) viennent des fonctions exactes du moteur (`playerActions`, `canBuildTransportShip`, drapeaux d'interaction).
`build_obs` produit l'observation ; `decode` produit l'intent. Types transitoires (Shell, SAMMissile, MIRVWarhead) : vecteur nul.

**Invariants a ne pas casser** (tests : `ofsi/rl2/test_model.py`, `diag_tf.py`) : echantillonnage et reevaluation (`act(actions=...)`) doivent donner des log-probabilites IDENTIQUES ; l'indice de pointeur est force a 0 pour les types sans pointeur AVANT usage.
Les types de joueur du moteur sont en MAJUSCULES (`BOT`/`NATION`/`HUMAN`).

## Reseau (`ofsi/rl2/model.py`)

Jetons (soi, joueurs, unites, attaques, grille geographique conv 8x8) -> transformer (d=128, 4 couches) -> decodeur autoregressif (type -> pointeur bilineaire -> parametre) + tete de valeur. 1,41 M parametres.
bf16 + TF32 sur GPU (mesure : 2,05x). Sur CPU : 2,3 s par pas (inutilisable).

## Pipeline d'experimentation

1. `skills.py`/`skills2.py`/`skills3.py` (`run_skills.py`) : scenarios de competence, effet verifie dans l'etat. **PASS = executable, pas "maitrise"**. Surcharges (or infini, construction instantanee) reservees aux scenarios.
2. `collect_v2.py` : demonstrations (obs compactes float16 + masques empaquetes). `pretrain.py --method bc|ssl|both` (split PAR EPISODE ; checkpoint = meilleure validation ; BC filtre = episodes gagnants).
3. `ppo2.py` : PPO masque, curriculum par difficulte, checkpoints SHA-256 (`ckpt.py`), reprise, `STOP`/`PAUSE`. `memguard.py` attend la RAM libre avant de lancer des moteurs.
4. `eval2.py` : evaluation sur parties a **seeds fixes** (cartes d'entrainement et cartes jamais vues), IC de Wilson ; `compare_paired.py` : McNemar exact apparie.
5. `league.py` + `env2_multi.py` : parties multi-agents, Bradley-Terry avec a priori faible, regle de promotion (borne de Wilson + absence de regression). `counterfactual.py` : alternatives depuis des snapshots exacts.
6. `report.py` : rapport automatique (n'inclut que des artefacts mesures ; sinon "NON MESURE").

## Regles de methode

* Aucun resultat sans fichier de preuve dans `benchmarks/`. Comparer sur les **memes parties** ; ne jamais conclure sur < ~50 parties sans le dire.
* Un resultat de partie est **sensible a de petits choix aleatoires** (meme graine, autre graine du professeur = victoire ou defaite) : l'echantillon compte.
* Chaque defaut trouve doit etre note dans `docs/JOURNAL.md` avec sa correction (nombreux defauts de tests, d'observation et d'action trouves par mesure : voir le journal).
* Ne jamais lancer plus de ~16 moteurs ni deux evaluations avec un preentrainement : voir `docs/JOURNAL.md` (contrainte memoire).
