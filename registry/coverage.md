# Matrice de couverture des intents (genere)

Moteur : commit `db8bf7c4`. Statut = presence dans l'espace d'actions v1 uniquement ; **aucune maitrise n'est revendiquee** (scenarios de competence non encore ecrits).

Resume : EXCLU=6, NON=14, PARTIEL=4, SCRIPTE=1

| intent | statut v1 | parametres moteur | note |
|---|---|---|---|
| allianceExtension | NON | recipient |  |
| allianceReject | NON | requestor |  |
| allianceRequest | PARTIEL | recipient | demande vers un des 6 voisins; l'acceptation d'une demande entrante passe par la meme action |
| attack | PARTIEL | targetID, troops | expand (cible neutre) + attaque d'un des 6 voisins frontaliers, fraction discrete; pas de choix de tuile/cible fine |
| boat | NON | troops, dst | attaque navale (transport) non encore dans l'espace d'actions |
| breakAlliance | NON | recipient |  |
| build_unit | PARTIEL | unit, tile, rocketDirectionUp, amount | City/Port/DefensePost/Factory/SAM/Warship, tuile choisie par script parmi tuiles legales moteur; silos/bombes/MIRV exclus |
| cancel_attack | NON | attackID | retraite non couverte |
| cancel_boat | NON | unitID |  |
| delete_unit | NON | unitId |  |
| donate_gold | NON | recipient, gold |  |
| donate_troops | NON | recipient, troops |  |
| embargo_all | NON | action |  |
| embargo | NON | targetID, action |  |
| emoji | PARTIEL | recipient, emoji | effet de jeu reel sur les NATIONS (relation -100/-10/+15 en Easy) ; 5 emojis utiles en parametre ; emoji vers tous (AllPlayers) non couvert |
| kick_player | EXCLU | targetClientID, targetPublicID | admin de lobby |
| mark_disconnected | EXCLU | isDisconnected | admin |
| move_warship | NON | unitIds, tile |  |
| quick_chat | EXCLU | recipient, quickChatKey, target | communication |
| spawn | SCRIPTE | tile | tuile aleatoire legale choisie par le harnais, PAS apprise (SpawnNet a venir) |
| targetPlayer | NON | target |  |
| toggle_game_start_timer | EXCLU |  | admin |
| toggle_pause | EXCLU | paused | admin |
| update_game_config | EXCLU | config | admin |
| upgrade_structure | NON | unit, unitId, amount | ameliorations non encore couvertes |
