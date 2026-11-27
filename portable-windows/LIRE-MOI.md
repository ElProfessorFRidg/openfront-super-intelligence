# OpenFront SI PR #1 · Windows x64 portable

Extrais tout le ZIP dans un dossier où tu peux écrire. Double-clique sur l'un des fichiers BAT. Garde la console ouverte pendant une partie ou pendant l'utilisation du tableau de bord.

| Fichier | Résultat |
| --- | --- |
| `TEST.bat` | 24 parties Medium, dont 8 sur les cartes inédites du protocole. Bilan par carte, victoires, durée et actions dans un rapport JSON. |
| `BENCHMARK.bat` | Débit du moteur en ticks/s et inférence réelle du champion sur CPU et sur les GPU CUDA utilisables. |
| `REPLAY.bat` | Une partie Onion visualisable dans le tableau de bord. |
| `DASHBOARD.bat` | Lancement de parties, visualisation en direct, rejeux et rapports JSON dans le navigateur. |

Dans le dashboard, sélectionne la carte, la difficulté, les bots et les nations, puis clique sur **Lancer la partie**. Le champion est sélectionné par défaut sur la carte. Survole un pays ou une unité pour l'inspecter. Les options permettent de masquer les bâtiments, bateaux et projectiles. **Relancer après une défaite** poursuit les essais jusqu'à une victoire confirmée par le moteur ou un arrêt manuel.

Si le navigateur ne s’ouvre pas, ouvre l’adresse affichée dans la console. Si le port 8765 est déjà utilisé, lance `.\DASHBOARD.bat --port 8766` depuis un terminal. En cas d’erreur sur les cartes ou le moteur, vérifie que le ZIP a été extrait en entier.

Les rapports sont dans `reports\` et les parties enregistrées dans `runs\_replays\`. Le fichier `distribution.json` identifie le moteur, le champion et les versions embarquées.

Le ZIP CPU cible les PC Windows 10/11 x64 Intel ou AMD récents. Le ZIP CUDA utilise CUDA 13.2 et requiert un GPU NVIDIA compatible et un pilote NVIDIA compatible déjà présent. Il utilise automatiquement le CPU si CUDA est indisponible. Aucun SDK CUDA, Python ou Node installé sur la machine n'est requis.

Depuis un terminal, `TEST.bat --quick` joue une partie courte pour vérifier le lancement. `BENCHMARK.bat --device cuda` exige un GPU CUDA fonctionnel et mesure aussi le CPU. `DASHBOARD.bat --port 8766` permet d'utiliser un autre port. Pour évaluer un autre checkpoint OpenFront SI v2, utilise par exemple `TEST.bat --checkpoint "C:\modeles\ckpt_latest.pt"` avec le fichier `ckpt_latest.pt.sha256` à côté.

Le moteur officiel OpenFront.io est fourni sous AGPL-3.0 et les cartes sous CC BY-SA 4.0. Les textes et crédits d’origine sont dans `vendor/openfront-engine/`. Le code et les scripts d’assemblage sont dans le dépôt privé OpenFront SI.
