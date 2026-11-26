# Usage: .\adapter\run_ts.ps1 <script relatif à adapter/> [args...]
# Copie adapter/ dans l'arbre du moteur (résolution des paquets @openfront/*) puis exécute avec Node 24 portable.
param([Parameter(Mandatory)][string]$Script,[Parameter(ValueFromRemainingArguments)][string[]]$Rest)
$root = Split-Path $PSScriptRoot -Parent
$eng  = Join-Path $root 'vendor\openfront-engine'
$env:PATH = "$root\tools\node24\node-v24.22.3-win-x64;$env:PATH"
robocopy $PSScriptRoot "$eng\osi" /MIR /XD node_modules /NFL /NDL /NJH /NJS /NP | Out-Null
Push-Location $eng
try { $env:ENGINE_COMMIT = (git rev-parse HEAD); & npx tsx "osi/$Script" @Rest } finally { Pop-Location }
