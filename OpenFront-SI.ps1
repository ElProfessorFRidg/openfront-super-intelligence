<#
  OpenFront Super Intelligence — lanceur local (Windows). Aucune cle API, aucun compte, aucun service permanent.
  Usage :  .\OpenFront-SI.ps1 <commande>
    setup      verifie/prepare l'environnement (Node portable, moteur, venv GPU), compile, smoke test, diagnostic CUDA
    doctor     diagnostic complet (GPU, RAM, disque, versions, checkpoints) sans rien modifier
    repair     reconstruit ce qui manque (adaptateur synchronise, dependances) sans toucher aux checkpoints
    dashboard  demarre le tableau de bord local (127.0.0.1 uniquement) et ouvre le navigateur
    train      lance/reprend l'entrainement PPO v2 en arriere-plan (arret propre : .\OpenFront-SI.ps1 stop)
    stop       demande l'arret propre (checkpoint sauvegarde) de tous les entrainements
    benchmark  mesure le debit du moteur et du GPU
    evaluate   evalue un checkpoint sur les parties de reference (seeds fixes) :  evaluate <checkpoint.pt>
    skills     execute les scenarios de competence (preuve que chaque mecanique s'execute)
  Le moteur tourne independamment de l'interface ; fermer le navigateur n'arrete rien.
#>
param([Parameter(Position=0)][string]$Cmd = "help", [Parameter(Position=1, ValueFromRemainingArguments=$true)][string[]]$Rest)
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot; Set-Location $Root
$Node = Join-Path $Root "tools\node24\node-v24.22.3-win-x64"
$PyGpu = Join-Path $Root ".venv-gpu\Scripts\python.exe"
function Say($m, $c = "Cyan") { Write-Host "[OpenFront-SI] $m" -ForegroundColor $c }

function Get-FreeRamGB { [math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB, 1) }

function Do-Doctor {
    Say "Diagnostic (lecture seule)"
    $ok = $true
    if (Test-Path "$Node\node.exe") { Say ("Node portable : " + (& "$Node\node.exe" -v)) "Green" } else { Say "Node 24 portable ABSENT : lancer 'setup'" "Red"; $ok = $false }
    if (Test-Path "vendor\openfront-engine\node_modules") { Say "Moteur officiel : dependances installees" "Green" } else { Say "Moteur : dependances absentes (lancer 'setup')" "Red"; $ok = $false }
    if (Test-Path $PyGpu) { Say "venv GPU : present" "Green" } else { Say "venv GPU absent : fallback CPU (python systeme) possible mais lent pour le reseau v2" "Yellow" }
    if (Test-Path $PyGpu) {
        $o = & $PyGpu -c "import torch;print(torch.__version__, 'cuda' if torch.cuda.is_available() else 'cpu', torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')" 2>&1
        if ($o -match "cuda") { Say "PyTorch : $o" "Green" } else { Say "PyTorch sans CUDA ($o). Verifier : secteur branche + mode graphique discret (la RTX 3050 n'est visible que dans ces conditions)." "Yellow" }
    }
    $free = Get-FreeRamGB; $disk = [math]::Round((Get-PSDrive C).Free / 1GB, 1)
    Say "RAM libre : $free Go ; disque libre : $disk Go" $(if ($free -lt 6 -or $disk -lt 5) { "Yellow" } else { "Green" })
    if ($free -lt 6) { Say "RAM faible : ne lancez pas plus de ~16 moteurs ; fermez OneDrive/navigateurs" "Yellow" }
    if ($disk -lt 5) { Say "Disque presque plein : les checkpoints/demos peuvent echouer" "Red" }
    $cpu = Get-CimInstance Win32_Processor | Select-Object -First 1; $pf = Get-CimInstance Win32_PerfFormattedData_Counters_ProcessorInformation | Where-Object { $_.Name -eq '_Total' }
    if ($cpu -and $pf) {
        $pct = [math]::Round(100 * $pf.ProcessorFrequency / $cpu.MaxClockSpeed)
        Say ("CPU : {0} MHz sur {1} MHz nominaux ({2} %)" -f $pf.ProcessorFrequency, $cpu.MaxClockSpeed, $pct) $(if ($pct -lt 60) { "Yellow" } else { "Green" })
        if ($pct -lt 60) { Say "Frequence CPU basse : mode constructeur silencieux/economie probable (MSI Center : choisir 'Extreme Performance', desactiver Ambient Silent). Debit d'entrainement divise par 2-3 mesure." "Yellow" }
    }
    Get-ChildItem runs -Directory -ErrorAction SilentlyContinue | ForEach-Object {
        $c = Join-Path $_.FullName "ckpt_latest.pt"; if (Test-Path $c) { $h = (Get-FileHash $c -Algorithm SHA256).Hash.ToLower(); $e = (Get-Content "$c.sha256" -ErrorAction SilentlyContinue); Say ("checkpoint " + $_.Name + " : " + $(if ($e -eq $h) { "integre (SHA-256 OK)" } else { "SOMME DE CONTROLE INVALIDE ou absente" })) $(if ($e -eq $h) { "Green" } else { "Red" }) }
    }
    return $ok
}

switch ($Cmd.ToLower()) {
    "doctor"    { [void](Do-Doctor) }
    "repair"    {
        Say "Reparation : synchronisation de l'adaptateur (les checkpoints ne sont pas touches)"
        & powershell -NoProfile -File "$Root\adapter\sync_adapter.ps1"
        if (-not (Test-Path "vendor\openfront-engine\node_modules")) { Say "Dependances du moteur absentes : relancer 'setup'" "Yellow" }
        [void](Do-Doctor)
    }
    "setup"     {
        if (-not (Test-Path "$Node\node.exe")) { Say "Node 24 portable absent. Telecharger depuis nodejs.org/dist/latest-v24.x (zip win-x64) et verifier le SHA256, extraire dans tools\node24\" "Red"; exit 1 }
        $env:PATH = "$Node;$env:PATH"
        if (-not (Test-Path "vendor\openfront-engine\node_modules")) { Push-Location vendor\openfront-engine; npm ci --ignore-scripts; Pop-Location }
        & powershell -NoProfile -File "$Root\adapter\sync_adapter.ps1"
        Say "Smoke test moteur + snapshot/restore"; python ofsi\test_client.py
        [void](Do-Doctor)
        Say "Setup termine. Etape suivante : .\OpenFront-SI.ps1 dashboard   puis   .\OpenFront-SI.ps1 train" "Green"
    }
    "dashboard" {
        & powershell -NoProfile -File "$Root\adapter\sync_adapter.ps1"
        $already = Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match "dashboard.py" }
        if (-not $already) { Start-Process -WindowStyle Hidden -FilePath python -ArgumentList "ofsi\dashboard.py" -WorkingDirectory $Root -RedirectStandardOutput "$Root\dashboard.log" -RedirectStandardError "$Root\dashboard.err" | Out-Null; Start-Sleep 2 }
        Say "Tableau de bord : http://127.0.0.1:8765 (loopback uniquement)" "Green"; Start-Process "http://127.0.0.1:8765"
    }
    "train"     {
        if ((Get-FreeRamGB) -lt 7) { Say "RAM libre insuffisante ($(Get-FreeRamGB) Go) : fermez d'autres applications avant d'entrainer" "Red"; exit 1 }
        $py = if (Test-Path $PyGpu) { $PyGpu } else { "python" }
        $name = if ($Rest.Count -ge 1) { $Rest[0] } else { "main" }
        $resume = if (Test-Path "runs\$name\ckpt_latest.pt") { @("--resume") } else { @() }
        Remove-Item "runs\$name\STOP" -ErrorAction SilentlyContinue
        # Recette PPO validee (docs/JOURNAL.md) : lr 1e-4, entropie 0,005 ; avec un checkpoint pre-entraine (2e argument) : 8 mises a jour d'echauffement de la valeur seule.
        $init = if ($Rest.Count -ge 2) { @("--init", $Rest[1], "--value-warmup", "8") } else { @() }
        $args = @("ofsi\rl2\ppo2.py", "--name", $name, "--envs", "8", "--lr", "1e-4", "--ent", "0.005") + $init + $resume
        Start-Process -WindowStyle Hidden -FilePath $py -ArgumentList $args -WorkingDirectory $Root -RedirectStandardOutput "$Root\runs_$name.log" -RedirectStandardError "$Root\runs_$name.err" | Out-Null
        Say "Entrainement '$name' lance en arriere-plan ($(if($resume){'reprise du checkpoint'}else{'nouveau'})). Suivi : .\OpenFront-SI.ps1 dashboard" "Green"
    }
    "stop"      {
        Get-ChildItem runs -Directory -ErrorAction SilentlyContinue | ForEach-Object { if (Test-Path "$($_.FullName)\metrics.jsonl") { New-Item -ItemType File -Force "$($_.FullName)\STOP" | Out-Null } }
        Say "Arret propre demande (chaque entrainement sauvegarde un checkpoint puis s'arrete)" "Green"
    }
    "benchmark" { & python ofsi\bench_parallel.py Onion 8 600 1,4,8,16; if (Test-Path $PyGpu) { & $PyGpu ofsi\bench_gpu.py } }
    "evaluate"  { if (-not $Rest) { Say "Usage : evaluate <checkpoint.pt>" "Red"; exit 1 }; & $PyGpu ofsi\rl2\eval2.py --agent $Rest[0] --per 2 --difficulties Easy,Medium --envs 8 }
    "skills"    { & python ofsi\run_skills.py "" --out benchmarks\skills_full.json }
    default     { Get-Help $PSCommandPath | Out-String | Write-Host }
}
