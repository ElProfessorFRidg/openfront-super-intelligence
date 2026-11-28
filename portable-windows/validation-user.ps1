param([switch]$RequireCuda)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$distribution = Join-Path $root "Distribution portable"
$log = Join-Path $root "validation.log"
$status = Join-Path $root "status.txt"
$env:Path = "$env:SystemRoot\System32;$env:SystemRoot"
$env:OFSI_NONINTERACTIVE = "1"
$env:PYTHONHOME = "C:\Python-externe-inexistant"
$env:PYTHONPATH = "C:\Python-externe-inexistant"
$env:TEMP = (New-Item -ItemType Directory -Force -Path (Join-Path $root "temp")).FullName
$env:TMP = $env:TEMP
$identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$command = "$env:SystemRoot\System32\cmd.exe"
$dashboardProcess = $null

function Invoke-Launcher([string]$name, [string]$arguments) {
    $stdout = Join-Path $root "$name.stdout"
    $stderr = Join-Path $root "$name.stderr"
    $file = Join-Path $distribution "$name.bat"
    $process = Start-Process -FilePath $command -ArgumentList ('/d /s /c ""{0}" {1}"' -f $file, $arguments) `
        -NoNewWindow -Wait -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    Get-Content -LiteralPath $stdout, $stderr | Add-Content -LiteralPath $log
    if ($process.ExitCode -ne 0) { throw "$name : code $($process.ExitCode)" }
}

$result = "FAIL"
try {
    "Utilisateur Windows : $identity | PATH système uniquement | dossier relocalisé avec espaces" |
        Set-Content -LiteralPath $log
    $runtime = Join-Path $distribution "python/python.exe"
    # A socket check proves the executable cannot reach a public service.
    & $runtime -c "import socket, sys
try:
    socket.create_connection(('1.1.1.1', 443), timeout=3).close()
except OSError:
    sys.exit(0)
sys.exit(1)"
    if ($LASTEXITCODE -ne 0) { throw "Accès réseau sortant autorisé pour le Python portable" }
    $device = if ($RequireCuda) { "--device cuda" } else { "" }
    Invoke-Launcher TEST "--quick $device"
    Invoke-Launcher BENCHMARK "--quick $device"
    Invoke-Launcher REPLAY "--quick $device"
    $reports = @(Get-ChildItem -LiteralPath (Join-Path $distribution "reports") -Filter "*.json")
    if ($reports.Count -ne 3) { throw "Trois rapports attendus" }
    foreach ($file in $reports) {
        $report = Get-Content -Raw -LiteralPath $file.FullName | ConvertFrom-Json
        if ($report.passed -ne $true -or $report.hardware.process_admin -ne $false) {
            throw "Rapport invalide ou processus élevé : $($file.Name)"
        }
        if ($RequireCuda -and $report.device -ne "cuda") { throw "CUDA non utilisé" }
        if ($report.command -eq "benchmark") {
            if ($report.result.engine.ticks -le 0) { throw "Aucun tick moteur mesuré" }
            if ($RequireCuda -and "cuda" -notin @($report.result.inference.device)) { throw "Inférence CUDA absente" }
        }
    }

    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
    $listener.Start()
    $port = $listener.LocalEndpoint.Port
    $listener.Stop()
    $dash = Join-Path $distribution "DASHBOARD.bat"
    $dashboardProcess = Start-Process -FilePath $command `
        -ArgumentList ('/d /s /c ""{0}" --no-browser --quick --port {1}"' -f $dash, $port) -PassThru -NoNewWindow `
        -RedirectStandardOutput (Join-Path $root "dashboard.stdout") `
        -RedirectStandardError (Join-Path $root "dashboard.stderr")
    $base = "http://127.0.0.1:$port"
    $deadline = (Get-Date).AddSeconds(30)
    do {
        try {
            $page = Invoke-WebRequest -Uri $base -UseBasicParsing -TimeoutSec 3
            break
        } catch {
            if ((Get-Date) -ge $deadline -or $dashboardProcess.HasExited) { throw }
            Start-Sleep -Seconds 1
        }
    } while ($true)
    if ($page.Content -notmatch 'rpCanvas') { throw "Visualiseur absent" }
    $replays = (Invoke-RestMethod -Uri "$base/api/replays")
    $replay = Invoke-RestMethod -Uri "$base/api/replay?name=$($replays[0].name)"
    if ($replay.frames.Count -lt 2 -or $replay.frames[0].grid.Length -ne ($replay.gw * $replay.gh)) {
        throw "Rejeu invalide"
    }
    $entries = (Invoke-RestMethod -Uri "$base/api/benchmarks")
    $download = Invoke-RestMethod -Uri "$base/reports/$($entries[0].file)"
    if ($entries.Count -ne 3 -or $download.passed -ne $true) { throw "Export JSON indisponible" }
    if ($page.Content -notmatch 'const SESSION_TOKEN = "([^"]+)"') { throw "Session du dashboard introuvable" }
    $token = $Matches[1]
    $options = Invoke-RestMethod -Uri "$base/api/options"
    if ($options.maps.Count -lt 10) { throw "Cartes du dashboard indisponibles" }
    $payload = @{
        map = "Onion"; difficulty = "Easy"; bots = 8; nations = $true; retry = $false
        seed = "rp000001"; device = $(if ($RequireCuda) { "cuda" } else { "cpu" })
    } | ConvertTo-Json -Compress
    Invoke-RestMethod -Method Post -Uri "$base/api/game" -ContentType "application/json" `
        -Headers @{"X-OpenFront-Session" = $token} -Body $payload | Out-Null
    $deadline = (Get-Date).AddSeconds(120)
    do {
        $game = Invoke-RestMethod -Uri "$base/api/game"
        if ($game.status -ne "running") { break }
        Start-Sleep -Milliseconds 300
    } while ((Get-Date) -lt $deadline)
    if (-not $game.replay) { throw "Partie lancee depuis le dashboard : $($game.message)" }
    $view = Invoke-RestMethod -Uri "$base/api/replay?name=$($game.replay)"
    if ($view.cfg.map -ne "Onion" -or $view.frames.Count -lt 2 -or -not $view.frames[0].owners -or $view.players.Count -lt 2) {
        throw "Rejeu detaille du dashboard invalide"
    }
    "PASS : lanceurs, export JSON et partie demarree depuis le dashboard." | Add-Content -LiteralPath $log
    $result = "PASS"
} catch {
    ($_ | Out-String) | Add-Content -LiteralPath $log
} finally {
    if ($dashboardProcess -and -not $dashboardProcess.HasExited) {
        & "$env:SystemRoot\System32\taskkill.exe" /T /F /PID $dashboardProcess.Id | Out-Null
    }
    $result | Set-Content -LiteralPath $status
}
