<#
  Moniteur systeme pour l'audit de performance (lecture seule). Echantillonne toutes les N secondes et ecrit un CSV :
  - par classe de coeur (P / E+LPE) : charge moyenne et frequence moyenne ; frequence max autorisee ;
  - GPU (nvidia-smi) : utilisation, horloge SM, puissance, temperature, memoire, raisons de bridage ;
  - RAM libre, zone thermique ACPI ; CPU cumule des processus node/python.
  Usage : powershell -File perf\sysmon.ps1 -Out perf\out\sysmon_x.csv -Seconds 120 -Every 2
  NB : l'echantillonnage lui-meme coute ~1-3 % d'un coeur ; a lancer de la MEME facon pour toutes les configurations comparees.
#>
param([string]$Out = "perf\out\sysmon.csv", [int]$Seconds = 60, [int]$Every = 2)
$ErrorActionPreference = "SilentlyContinue"
New-Item -ItemType Directory -Force (Split-Path $Out) | Out-Null
$P  = 0,1,10,11,12,13,14,15,16,17,18,19            # classe d'efficacite 1 (voir perf/topology.json)
$EL = 2,3,4,5,6,7,8,9,20,21                         # classe 0 : E-cores + LP E-cores
"t,cpu_total_pct,cpu_freq_mhz_total,p_load_pct,p_freq_mhz,e_load_pct,e_freq_mhz,max_allowed_mhz,gpu_util_pct,gpu_sm_mhz,gpu_power_w,gpu_temp_c,gpu_mem_mb,gpu_throttle,ram_free_gb,thermal_c,node_cpu_s,python_cpu_s,node_count" | Out-File $Out -Encoding utf8
$t0 = Get-Date
while (((Get-Date) - $t0).TotalSeconds -lt $Seconds) {
    $c = Get-CimInstance Win32_PerfFormattedData_Counters_ProcessorInformation
    $cores = $c | Where-Object { $_.Name -match '^0,(\d+)$' } | ForEach-Object { [pscustomobject]@{ I = [int]($_.Name -split ',')[1]; Load = $_.PercentProcessorUtility; Freq = $_.ProcessorFrequency; Pct = $_.PercentofMaximumFrequency } }
    $p = $cores | Where-Object { $P -contains $_.I }; $e = $cores | Where-Object { $EL -contains $_.I }; $tot = $c | Where-Object { $_.Name -eq '_Total' }
    $g = (nvidia-smi --query-gpu=utilization.gpu, clocks.sm, power.draw, temperature.gpu, memory.used, clocks_throttle_reasons.active --format=csv, noheader, nounits) -split ',\s*'
    $os = Get-CimInstance Win32_OperatingSystem; $th = Get-CimInstance Win32_PerfFormattedData_Counters_ThermalZoneInformation | Select-Object -First 1
    $node = Get-Process node; $py = Get-Process python
    $maxMhz = ($cores | Measure-Object Freq -Maximum).Maximum
    "{0:N0},{1},{2},{3:N1},{4:N0},{5:N1},{6:N0},{7},{8},{9},{10},{11},{12},{13},{14:N1},{15:N0},{16:N0},{17:N0},{18}" -f ((Get-Date) - $t0).TotalSeconds, $tot.PercentProcessorUtility, $tot.ProcessorFrequency, ($p | Measure-Object Load -Average).Average, ($p | Measure-Object Freq -Average).Average, ($e | Measure-Object Load -Average).Average, ($e | Measure-Object Freq -Average).Average, $maxMhz, $g[0], $g[1], $g[2], $g[3], $g[4], $g[5], ($os.FreePhysicalMemory / 1MB), ($th.Temperature - 273.15), ($node | Measure-Object CPU -Sum).Sum, ($py | Measure-Object CPU -Sum).Sum, ($node | Measure-Object).Count | Out-File $Out -Append -Encoding utf8
    Start-Sleep $Every
}
Write-Host "echantillons ecrits dans $Out"
