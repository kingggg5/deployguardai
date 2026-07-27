$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$runtimeRoot = Join-Path $projectRoot '.runtime'

function Stop-ProjectProcessTree {
    param(
        [Parameter(Mandatory)]
        [int]$RootProcessId
    )

    $rootProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $RootProcessId" -ErrorAction SilentlyContinue
    if ($null -eq $rootProcess) {
        return $false
    }

    if ($rootProcess.CommandLine -notlike "*$projectRoot*") {
        Write-Warning "Skipped PID $RootProcessId because it no longer belongs to this project."
        return $false
    }

    $processIds = [System.Collections.Generic.List[int]]::new()
    $pendingIds = [System.Collections.Generic.Queue[int]]::new()
    $pendingIds.Enqueue($RootProcessId)

    while ($pendingIds.Count -gt 0) {
        $parentId = $pendingIds.Dequeue()
        $processIds.Add($parentId)
        $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $parentId" -ErrorAction SilentlyContinue
        foreach ($child in $children) {
            $pendingIds.Enqueue([int]$child.ProcessId)
        }
    }

    for ($index = $processIds.Count - 1; $index -ge 0; $index--) {
        Stop-Process -Id $processIds[$index] -ErrorAction SilentlyContinue
    }
    return $true
}

foreach ($name in @('backend', 'frontend')) {
    $pidPath = Join-Path $runtimeRoot "$name.pid"
    if (-not (Test-Path -LiteralPath $pidPath)) {
        continue
    }

    $processId = [int](Get-Content -LiteralPath $pidPath -Raw)
    if ($null -ne (Get-Process -Id $processId -ErrorAction SilentlyContinue)) {
        if (Stop-ProjectProcessTree -RootProcessId $processId) {
            Write-Output "Stopped $name (PID $processId)"
        }
    }

    Remove-Item -LiteralPath $pidPath -Force
}
