# Matrice de preuves des mecaniques (generee)

Moteur `db8bf7c4` ; espace d'actions v2 : 32 types, banque de 312 candidats. Resume intents de gameplay : {'valide': 19, 'non_valide': 0, 'sans_scenario': 0}.

| intent moteur | statut | types d'action v2 | scenarios de competence (effet verifie) | demonstrations (decisions) | note |
|---|---|---|---|---|---|
| allianceExtension | COUVERT v2 | ALLY_EXTEND | alliance: PASS | ALLY_EXTEND=0 |  |
| allianceReject | COUVERT v2 | ALLY_REJECT | alliance_reject: PASS | ALLY_REJECT=0 |  |
| allianceRequest | COUVERT v2 | ALLY_REQUEST | alliance: PASS; tribes_accept_alliance: PASS | ALLY_REQUEST=3887 |  |
| attack | COUVERT v2 | ATTACK_NEUTRAL ATTACK_PLAYER | attack_neutral: PASS; attack_player: PASS | ATTACK_NEUTRAL=11809, ATTACK_PLAYER=4313 |  |
| boat | COUVERT v2 | BOAT | boat: PASS | BOAT=3115 |  |
| breakAlliance | COUVERT v2 | ALLY_BREAK | alliance: PASS | ALLY_BREAK=0 |  |
| build_unit | COUVERT v2 | BUILD_City BUILD_Port BUILD_Defense Post BUILD_Factory BUILD_SAM Launcher BUILD_Missile Silo BUILD_Warship NUKE_Atom Bomb NUKE_Hydrogen Bomb NUKE_MIRV | build_City: PASS; build_Port: PASS; build_Defense Post: PASS; build_Factory: PASS; build_SAM Launcher: PASS; build_Missile Silo: PASS; warship: PASS; nuke_atom: PASS; nuke_hydrogen: PASS; nuke_mirv: PASS; sam_intercept: PASS | BUILD_City=3177, BUILD_Port=308, BUILD_Defense Post=848, BUILD_Factory=352 |  |
| cancel_attack | COUVERT v2 | CANCEL_ATTACK | cancel_attack: PASS | CANCEL_ATTACK=0 |  |
| cancel_boat | COUVERT v2 | CANCEL_BOAT | cancel_boat: PASS | CANCEL_BOAT=0 |  |
| delete_unit | COUVERT v2 | DELETE_UNIT | delete_unit: PASS | DELETE_UNIT=0 |  |
| donate_gold | COUVERT v2 | DONATE_GOLD | donate: PASS | DONATE_GOLD=0 |  |
| donate_troops | COUVERT v2 | DONATE_TROOPS | donate: PASS | DONATE_TROOPS=0 |  |
| embargo_all | COUVERT v2 | EMBARGO_ALL_ON EMBARGO_ALL_OFF | embargo_all: PASS | EMBARGO_ALL_ON=0, EMBARGO_ALL_OFF=0 |  |
| embargo | COUVERT v2 | EMBARGO_ON EMBARGO_OFF | embargo: PASS | EMBARGO_ON=0, EMBARGO_OFF=0 |  |
| emoji | COUVERT v2 | EMOJI | emoji_effet_relation: PASS | EMOJI=0 |  |
| kick_player | EXCLU | - | - | - | administration de lobby |
| mark_disconnected | EXCLU | - | - | - | administration |
| move_warship | COUVERT v2 | MOVE_WARSHIPS | warship: PASS | MOVE_WARSHIPS=0 |  |
| quick_chat | EXCLU | - | - | - | texte pre-defini sans effet de jeu documente (les nations ignorent les Quick Chat) |
| spawn | COUVERT v2 | SPAWN | spawn: PASS | SPAWN=148 |  |
| targetPlayer | COUVERT v2 | TARGET_PLAYER | target_player: PASS | TARGET_PLAYER=0 |  |
| toggle_game_start_timer | EXCLU | - | - | - | administration |
| toggle_pause | EXCLU | - | - | - | administration |
| update_game_config | EXCLU | - | - | - | administration |
| upgrade_structure | COUVERT v2 | UPGRADE | upgrade_structure: PASS | UPGRADE=896 |  |
