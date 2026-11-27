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
$password = "OFSI-aA1-" + [Guid]::NewGuid().ToString("N")

$expected = (Get-Content -Raw -LiteralPath "$zipFile.sha256").Trim()
if ((Get-FileHash -LiteralPath $zipFile).Hash -ne $expected) { throw "ZIP corrompu" }
try {
    New-Item -ItemType Directory -Path $root, $distribution | Out-Null
    & $sevenZip x -y -bso0 "-o$distribution" $zipFile
    $user = New-LocalUser -Name $name -Password (ConvertTo-SecureString $password -AsPlainText -Force)
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
    $action = New-ScheduledTaskAction -Execute $systemPs -Argument $args -WorkingDirectory $root
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 18)
    Register-ScheduledTask -TaskName $task -Action $action -Settings $settings -User $account `
        -Password $password -RunLevel Limited | Out-Null
    Start-ScheduledTask -TaskName $task
    $deadline = (Get-Date).AddMinutes(18)
    $done = Join-Path $root "status.txt"
    while (-not (Test-Path -LiteralPath $done) -and (Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 5
    }
    if (-not (Test-Path -LiteralPath $done)) {
        $info = Get-ScheduledTaskInfo -TaskName $task
        throw "Validation expirée, dernier résultat du Planificateur : $($info.LastTaskResult)"
    }
    if ((Get-Content -Raw -LiteralPath $done).Trim() -ne "PASS") { throw "Validation Windows échouée" }
} finally {
    $log = Join-Path $root "validation.log"
    if (Test-Path -LiteralPath $log) {
        Get-Content -LiteralPath $log
        Copy-Item -LiteralPath $log -Destination (Join-Path $output "validation.log")
    }
    $reports = Join-Path $distribution "reports"
    if (Test-Path -LiteralPath $reports) {
        Copy-Item -LiteralPath $reports -Destination (Join-Path $output "validation-reports") -Recurse -Force
    }
    if (Get-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue) {
        Stop-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $task -Confirm:$false
    }
    Get-NetFirewallRule -Group $task -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    if (Get-LocalUser -Name $name -ErrorAction SilentlyContinue) { Remove-LocalUser -Name $name }
    Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
}
