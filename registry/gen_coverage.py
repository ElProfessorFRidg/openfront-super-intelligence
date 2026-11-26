"""Genere registry/coverage.md depuis registry/mechanics.json (verite moteur) + etat de support de l'espace d'actions v1 (declare ici, a tenir a jour)."""
import json, pathlib
R = pathlib.Path(__file__).parent
mech = json.loads((R / "mechanics.json").read_text(encoding="utf-8"))
# etat : (couverture dans l'action space v1, note). Rien n'est marque "maitrise" : la maitrise exige un scenario de test dedie + mesure (non fait).
S = {
 "attack": ("PARTIEL", "expand (cible neutre) + attaque d'un des 6 voisins frontaliers, fraction discrete; pas de choix de tuile/cible fine"),
 "boat": ("NON", "attaque navale (transport) non encore dans l'espace d'actions"),
 "build_unit": ("PARTIEL", "City/Port/DefensePost/Factory/SAM/Warship, tuile choisie par script parmi tuiles legales moteur; silos/bombes/MIRV exclus"),
 "upgrade_structure": ("NON", "ameliorations non encore couvertes"),
 "allianceRequest": ("PARTIEL", "demande vers un des 6 voisins; l'acceptation d'une demande entrante passe par la meme action"),
 "allianceReject": ("NON", ""), "allianceExtension": ("NON", ""), "breakAlliance": ("NON", ""),
 "targetPlayer": ("NON", ""), "donate_gold": ("NON", ""), "donate_troops": ("NON", ""),
 "embargo": ("NON", ""), "embargo_all": ("NON", ""),
 "cancel_attack": ("NON", "retraite non couverte"), "cancel_boat": ("NON", ""), "move_warship": ("NON", ""), "delete_unit": ("NON", ""),
 "spawn": ("SCRIPTE", "tuile aleatoire legale choisie par le harnais, PAS apprise (SpawnNet a venir)"),
 "emoji": ("PARTIEL", "effet de jeu reel sur les NATIONS (relation -100/-10/+15 en Easy) ; 5 emojis utiles en parametre ; emoji vers tous (AllPlayers) non couvert"), "quick_chat": ("EXCLU", "communication"),
 "kick_player": ("EXCLU", "admin de lobby"), "mark_disconnected": ("EXCLU", "admin"), "toggle_pause": ("EXCLU", "admin"),
 "update_game_config": ("EXCLU", "admin"), "toggle_game_start_timer": ("EXCLU", "admin"),
}
rows = []
for name, f in mech["intents"].items():
    t = f.get("type", "").replace("literal:", "")
    st, note = S.get(t, ("INCONNU", "a classer"))
    rows.append((t, st, note, ", ".join(k for k in f if k != "type")))
cnt = {}
for r in rows: cnt[r[1]] = cnt.get(r[1], 0) + 1
out = ["# Matrice de couverture des intents (genere)", "", f"Moteur : commit `{mech['engine_commit'][:8]}`. Statut = presence dans l'espace d'actions v1 uniquement ; **aucune maitrise n'est revendiquee** (scenarios de competence non encore ecrits).", "",
       "Resume : " + ", ".join(f"{k}={v}" for k, v in sorted(cnt.items())), "", "| intent | statut v1 | parametres moteur | note |", "|---|---|---|---|"]
out += [f"| {t} | {st} | {p} | {n} |" for t, st, n, p in [(a, b, c, d) for a, b, c, d in rows]]
(R / "coverage.md").write_text("\n".join(out) + "\n", encoding="utf-8"); print("\n".join(out[:6]))
