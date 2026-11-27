param(
    [Parameter(Mandatory)][string]$Zip,
    [switch]$RequireCuda
)
$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true
$zipFile = (Resolve-Path -LiteralPath $Zip).Path
$output = Split-Path $zipFile -Parent
$identity = [Guid]::NewGuid().ToString("N").Substring(0, 8)
$root = Join-Path $env:PUBLIC "OFSI $identity validation"
$distribution = Join-Path $root "Distribution portable"
$name = "ofsi_$identity"
$account = "$env:COMPUTERNAME\$name"
$task = "OpenFrontPortable-$identity"
$systemPs = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$sevenZip = Join-Path $env:ProgramFiles "7-Zip/7z.exe"
$password = ConvertTo-SecureString ("OFSI-aA1-" + [Guid]::NewGuid().ToString("N")) -AsPlainText -Force
$stdout = Join-Path $root "child.stdout"
$stderr = Join-Path $root "child.stderr"
$worker = $null

$expected = (Get-Content -Raw -LiteralPath "$zipFile.sha256").Trim()
if ((Get-FileHash -LiteralPath $zipFile).Hash -ne $expected) { throw "ZIP corrompu" }
try {
    New-Item -ItemType Directory -Path $root, $distribution | Out-Null
    Write-Host "Extracting ZIP for relocated Windows test"
    & $sevenZip x -y -bso0 "-o$distribution" $zipFile
    $user = New-LocalUser -Name $name -Password $password
    $usersSid = "S-1-5-32-545"
    if (-not (Get-LocalGroupMember -SID $usersSid | Where-Object SID -eq $user.SID)) {
        Add-LocalGroupMember -SID $usersSid -Member $user
    }
    icacls $root /grant "${account}:(OI)(CI)M" /Q
    foreach ($program in @("python/python.exe", "node/node.exe")) {
        New-NetFirewallRule -DisplayName "$task-$program" -Group $task -Direction Outbound -Action Block `
            -Program (Join-Path $distribution $program) `
            -RemoteAddress @("0.0.0.0-126.255.255.255", "128.0.0.0-255.255.255.255", "::2-ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff") |
            Out-Null
    }

    $child = Join-Path $root "validation.ps1"
    Copy-Item -LiteralPath "$PSScriptRoot/validation-user.ps1" -Destination $child
    $args = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$child`""
    if ($RequireCuda) { $args += " -RequireCuda" }
    $service = Get-Service -Name seclogon
    if ($service.Status -ne "Running") { Start-Service -Name seclogon }
    $credential = [PSCredential]::new($account, $password)
    Write-Host "Starting validation as $account"
    $worker = Start-Process -FilePath $systemPs -ArgumentList $args -WorkingDirectory $root `
        -Credential $credential -LoadUserProfile -RedirectStandardOutput $stdout `
        -RedirectStandardError $stderr -PassThru
    if (-not $worker.WaitForExit(90000)) { throw "Validation Windows expirée (10 minutes)" }
    $done = Join-Path $root "status.txt"
    if ($worker.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $done)) {
        throw "Processus de validation interrompu, code $($worker.ExitCode)"
    }
    if ((Get-Content -Raw -LiteralPath $done).Trim() -ne "PASS") { throw "Validation Windows échouée" }
} finally {
    if ($worker -and -not $worker.HasExited) {
        & "$env:SystemRoot/System32/taskkill.exe" /T /F /PID $worker.Id | Out-Null
    }
    foreach ($file in @($stdout, $stderr)) {
        if (Test-Path -LiteralPath $file) { Get-Content -LiteralPath $file }
    }
    $log = Join-Path $root "validation.log"
    if (Test-Path -LiteralPath $log) {
        Get-Content -LiteralPath $log
        Copy-Item -LiteralPath $log -Destination (Join-Path $output "validation.log")
    }
    $reports = Join-Path $distribution "reports"
    if (Test-Path -LiteralPath $reports) {
        Copy-Item -LiteralPath $reports -Destination (Join-Path $output "validation-reports") -Recurse -Force
    }
    Get-NetFirewallRule -Group $task -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    if (Get-LocalUser -Name $name -ErrorAction SilentlyContinue) { Remove-LocalUser -Name $name }
    Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
}
