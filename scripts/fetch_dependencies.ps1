<#
  Recree les dependances EXCLUES du depot (versions epinglees, verifiees au moment du developpement).
  1) depots de reference clones dans vendor/ aux commits epingles ; 2) Node 24 portable (zip officiel + SHA256) ; 3) venv GPU PyTorch cu126 ; 4) dependances npm du moteur.
  Licences : le moteur est AGPL-3.0 ; openfront-ai n'a AUCUNE licence (etude seulement, ne jamais copier son code).
#>
$ErrorActionPreference = "Stop"; $Root = Split-Path $PSScriptRoot -Parent; Set-Location $Root
New-Item -ItemType Directory -Force vendor, tools\dl | Out-Null
$repos = @(
  @{ n = "openfront-engine"; u = "https://github.com/openfrontio/OpenFrontIO";        c = "db8bf7c4195bd3e2e4fb7936889dc406b42fe44a" },
  @{ n = "openfront-ai";     u = "https://github.com/djmango/openfront-ai";           c = "474536340480659c53d9a9e497b08fa1fefb9589" },
  @{ n = "openfront-agents"; u = "https://github.com/PeytonWDYM/OpenFront_Agents";    c = "334ee54b15db310b099759497819ea548e938f28" })
foreach ($r in $repos) { $d = "vendor\$($r.n)"; if (-not (Test-Path $d)) { git clone $r.u $d; git -C $d checkout $r.c } else { Write-Host "$d deja present" } }
$nodeDir = "tools\node24\node-v24.22.3-win-x64"
if (-not (Test-Path "$nodeDir\node.exe")) {
  $name = "node-v24.22.3-win-x64.zip"; $base = "https://nodejs.org/dist/v24.22.3"
  Invoke-WebRequest "$base/$name" -OutFile "tools\dl\$name"; $sums = (Invoke-RestMethod "$base/SHASUMS256.txt") -split "`n"
  $want = (($sums | Where-Object { $_ -match [regex]::Escape($name) }) -split '\s+')[0]; $got = (Get-FileHash "tools\dl\$name" -Algorithm SHA256).Hash.ToLower()
  if ($want -ne $got) { throw "SHA256 Node different : telechargement rejete" }
  Expand-Archive "tools\dl\$name" -DestinationPath tools\node24 -Force
  $env:PATH = "$Root\$nodeDir;$env:PATH"; npm install -g npm@12 --prefix "$Root\$nodeDir"
}
$env:PATH = "$Root\$nodeDir;$env:PATH"
if (-not (Test-Path "vendor\openfront-engine\node_modules")) { Push-Location vendor\openfront-engine; npm ci --ignore-scripts; Pop-Location }
if (-not (Test-Path ".venv-gpu")) {
  python -m venv .venv-gpu
  & .venv-gpu\Scripts\python.exe -m pip install --no-input numpy torch --index-url https://download.pytorch.org/whl/cu126 --extra-index-url https://pypi.org/simple
}
& powershell -NoProfile -File adapter\sync_adapter.ps1
Write-Host "Dependances pretes. Ensuite : .\OpenFront-SI.ps1 doctor" -ForegroundColor Green
