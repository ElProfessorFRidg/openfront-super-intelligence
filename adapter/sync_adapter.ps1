# Copie adapter/ dans l'arbre du moteur (résolution @openfront/*). À lancer une fois avant d'exécuter des démons.
$root = Split-Path $PSScriptRoot -Parent
robocopy $PSScriptRoot "$root\vendor\openfront-engine\osi" /MIR /XD node_modules /NFL /NDL /NJH /NJS /NP | Out-Null
exit 0
