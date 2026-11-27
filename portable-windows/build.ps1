param(
    [Parameter(Mandatory)][ValidateSet("cpu", "cuda")][string]$Variant,
    [Parameter(Mandatory)][string]$Output
)
$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = (Get-Command python -CommandType Application | Select-Object -First 1).Source
$engineCommit = "db8bf7c4195bd3e2e4fb7936889dc406b42fe44a"
$expectedChampion = "32654699e326ee8ee7ec35affb9387c878f4b9a2d59b65f95686184b7691da7b"
$champion = "runs/arm_C_medium/ckpt_latest.pt"
$sourcePr = if ($env:OFSI_PR_HEAD) { $env:OFSI_PR_HEAD } else { git -C $repo rev-parse HEAD }
$nodeVersion = "24.22.3"
$npmVersion = "12.2.3"
$pythonVersion = "3.13.13"
$torchVersion = "2.15.0"
$artifacts = (New-Item -ItemType Directory -Force -Path $Output).FullName
$zip = Join-Path $artifacts "OpenFront-SI-PR1-Windows-x64-$Variant.zip"
$build = Join-Path $env:RUNNER_TEMP ("ofsi-" + [Guid]::NewGuid().ToString("N").Substring(0, 8))
$stage = Join-Path $build "stage"
New-Item -ItemType Directory -Path $stage -Force | Out-Null

function Assert-Hash($file, $expected) {
    $digest = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($digest -ne $expected) { throw "SHA-256 inattendu : $file ($digest)" }
}

try {
    Write-Host "Preparing OpenFront engine at $engineCommit"
    $engine = Join-Path $stage "vendor/openfront-engine"
    New-Item -ItemType Directory -Path $engine -Force | Out-Null
    $env:GIT_LFS_SKIP_SMUDGE = "1"
    git -C $engine init --quiet
    git -C $engine -c core.longpaths=true fetch --depth=1 --no-tags https://github.com/openfrontio/OpenFrontIO.git $engineCommit
    git -C $engine -c core.longpaths=true checkout --quiet --detach FETCH_HEAD
    if ((git -C $engine rev-parse HEAD) -ne $engineCommit) { throw "Révision du moteur inattendue" }
    foreach ($path in @(".git", "proprietary", "map-generator/assets")) {
        Remove-Item -LiteralPath (Join-Path $engine $path) -Recurse -Force
    }
    Copy-Item -LiteralPath (Join-Path $repo "adapter") -Destination (Join-Path $engine "osi") -Recurse

    $pythonZip = Join-Path $build "python.zip"
    Invoke-WebRequest "https://www.python.org/ftp/python/$pythonVersion/python-$pythonVersion-embed-amd64.zip" -OutFile $pythonZip
    Assert-Hash $pythonZip "8766a8775746235e23cf5aee5027ab1060bb981d93110577adcf3508aa0cbd55"
    $runtime = Join-Path $stage "python"
    Expand-Archive -LiteralPath $pythonZip -DestinationPath $runtime
    @("python313.zip", ".", "site-packages", "..") |
        Set-Content -LiteralPath (Join-Path $runtime "python313._pth") -Encoding ascii

    $nodeZip = Join-Path $build "node.zip"
    $nodeName = "node-v$nodeVersion-win-x64"
    Invoke-WebRequest "https://nodejs.org/dist/v$nodeVersion/$nodeName.zip" -OutFile $nodeZip
    Assert-Hash $nodeZip "e612af99f626ab415ea225af6bce5c971feb448cb5cae250bb1c3fa50c5f7d9f"
    Expand-Archive -LiteralPath $nodeZip -DestinationPath $build
    $node = Join-Path $stage "node"
    Move-Item -LiteralPath (Join-Path $build $nodeName) -Destination $node
    $env:Path = "$node;$env:Path"
    $npmCli = Join-Path $node "node_modules/npm/bin/npm-cli.js"
    & "$node/node.exe" $npmCli install --global --prefix $node "npm@$npmVersion" --no-audit --no-fund --ignore-scripts
    if ((& "$node/node.exe" $npmCli --version) -ne $npmVersion) { throw "Version npm inattendue" }
    Push-Location $engine
    try {
        & "$node/node.exe" $npmCli ci --ignore-scripts --no-audit --no-fund
    } finally {
        Pop-Location
    }
    & $python "$PSScriptRoot/materialize.py" $engine
    $env:ENGINE_COMMIT = $engineCommit
    $env:TSX_DISABLE_CACHE = "1"
    Push-Location $engine
    try {
        & "$node/node.exe" --import tsx osi/scripts/selftest_snapshot.mts
    } finally {
        Pop-Location
    }

    $wheel = @{
        cpu = @{ tag = "cpu"; sha = "086f79c78c941b428410dc15f898ce2420a4580ae6983ea314692d71ce76c619" }
        cuda = @{ tag = "cu132"; sha = "7b54774dedca2a1147f1ae47451d9a8a7e88b80665fc505bf6a4f1f427d21e97" }
    }[$Variant]
    $torch = "torch @ https://download-r2.pytorch.org/whl/$($wheel.tag)/torch-$torchVersion%2B$($wheel.tag)-cp313-cp313-win_amd64.whl#sha256=$($wheel.sha)"
    Write-Host "Bundling PyTorch $torchVersion+$($wheel.tag)"
    $requirements = Join-Path $build "requirements.txt"
    ((Get-Content -LiteralPath (Join-Path $repo "requirements-lock.txt") | Where-Object { $_ -notmatch '^torch==' }) + $torch) |
        Set-Content -LiteralPath $requirements -Encoding ascii
    & $python -m pip --disable-pip-version-check install --no-cache-dir --no-compile --only-binary=:all: --target "$runtime/site-packages" -r $requirements

    # Keep the VC runtime beside the executables so the target machine needs no installer.
    $vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio/Installer/vswhere.exe"
    $vs = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if (-not $vs) { throw "SDK Visual C++ introuvable sur le runner de build" }
    $crt = Get-ChildItem -Path "$vs/VC/Redist/MSVC/*/x64/Microsoft.VC*.CRT" -Directory |
        Sort-Object { [version]$_.Parent.Parent.Name } -Descending | Select-Object -First 1
    if (-not $crt) { throw "CRT x64 redistribuable introuvable" }
    Get-ChildItem -LiteralPath $crt.FullName -Filter "*.dll" | Copy-Item -Destination $runtime
    Get-ChildItem -LiteralPath $crt.FullName -Filter "*.dll" | Copy-Item -Destination $node

    Copy-Item -LiteralPath (Join-Path $repo "ofsi") -Destination $stage -Recurse
    foreach ($file in @("portable.py", "live_dashboard.py", "dashboard-live.html", "dashboard-live.js", "TEST.bat", "BENCHMARK.bat", "DASHBOARD.bat", "REPLAY.bat", "LIRE-MOI.md")) {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot $file) -Destination $stage
    }
    $target = Join-Path $stage $champion
    New-Item -ItemType Directory -Path (Split-Path $target -Parent) -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $repo $champion) -Destination $target
    Copy-Item -LiteralPath (Join-Path $repo "$champion.sha256") -Destination "$target.sha256"
    Assert-Hash $target $expectedChampion
    if ((Get-Content -Raw -LiteralPath "$target.sha256").Trim() -ne $expectedChampion) {
        throw "Empreinte du champion incohérente dans la PR"
    }
    @{
        source_pr_commit = $sourcePr
        package_commit = (git -C $repo rev-parse HEAD)
        engine_commit = $engineCommit
        checkpoint = $champion
        checkpoint_sha256 = $expectedChampion
        variant = $Variant
        node = $nodeVersion
        npm = $npmVersion
        python = $pythonVersion
        torch = "$torchVersion+$($wheel.tag)"
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $stage "distribution.json") -Encoding utf8
    Write-Host "Creating $zip"
    $sevenZip = Join-Path $env:ProgramFiles "7-Zip/7z.exe"
    Push-Location $stage
    try {
        Remove-Item -LiteralPath $zip -ErrorAction SilentlyContinue
        & $sevenZip a -tzip -mx=3 -bso0 $zip ".\*"
    } finally {
        Pop-Location
    }
    (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant() |
        Set-Content -LiteralPath "$zip.sha256" -Encoding ascii
} finally {
    Remove-Item -LiteralPath $build -Recurse -Force
}
