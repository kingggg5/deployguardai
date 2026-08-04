param(
    [switch]$SkipInstall
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$backendRoot = Join-Path $projectRoot 'backend'
$frontendRoot = Join-Path $projectRoot 'frontend'
$runtimeRoot = Join-Path $projectRoot '.runtime'
$venvRoot = Join-Path $backendRoot '.venv'
$pythonExe = Join-Path $venvRoot 'Scripts\python.exe'
$nodeExe = (Get-Command node.exe -ErrorAction Stop).Source
$angularCli = Join-Path $frontendRoot 'node_modules\@angular\cli\bin\ng.js'

New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null

foreach ($name in @('backend', 'worker', 'frontend')) {
    $pidPath = Join-Path $runtimeRoot "$name.pid"
    if (-not (Test-Path -LiteralPath $pidPath)) {
        continue
    }

    $pidText = (Get-Content -LiteralPath $pidPath -Raw).Trim()
    if ($pidText -match '^[1-9]\d*$') {
        $existingProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $pidText" -ErrorAction SilentlyContinue
        if ($null -ne $existingProcess -and $existingProcess.CommandLine -like "*$projectRoot*") {
            throw "DeployGuard $name is already running (PID $pidText). Run scripts/stop-dev.ps1 first."
        }
    }

    Remove-Item -LiteralPath $pidPath -Force
}

# Keep the source helper in connected mode even when an older backend-local
# SQLite database contains synthetic records. Operators may supply DATABASE_URL
# for an intentionally chosen local PostgreSQL/SQLite database; the helper
# never enables synthetic seeding.
if ([string]::IsNullOrWhiteSpace($env:DATABASE_URL)) {
    $localDatabasePath = (Join-Path $runtimeRoot 'connected-local.db').Replace('\', '/')
    $env:DATABASE_URL = "sqlite:///$localDatabasePath"
}
$env:SEED_SYNTHETIC_DATA = 'false'

if (-not (Test-Path -LiteralPath $pythonExe)) {
    python -m venv $venvRoot
}

if (-not $SkipInstall) {
    & $pythonExe -m pip install --disable-pip-version-check -r (Join-Path $backendRoot 'requirements.txt')
    if (-not (Test-Path -LiteralPath (Join-Path $frontendRoot 'node_modules'))) {
        npm --prefix $frontendRoot install
    }
}

$backendOut = Join-Path $runtimeRoot 'backend.stdout.log'
$backendErr = Join-Path $runtimeRoot 'backend.stderr.log'
$workerOut = Join-Path $runtimeRoot 'worker.stdout.log'
$workerErr = Join-Path $runtimeRoot 'worker.stderr.log'
$frontendOut = Join-Path $runtimeRoot 'frontend.stdout.log'
$frontendErr = Join-Path $runtimeRoot 'frontend.stderr.log'

$backendProcess = Start-Process `
    -FilePath $pythonExe `
    -ArgumentList '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8100', '--reload' `
    -WorkingDirectory $backendRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $backendOut `
    -RedirectStandardError $backendErr `
    -PassThru

$apiReady = $false
for ($attempt = 0; $attempt -lt 60; $attempt++) {
    if ($backendProcess.HasExited) {
        break
    }
    try {
        $response = Invoke-WebRequest `
            -Uri 'http://127.0.0.1:8100/api/v1/health/ready' `
            -TimeoutSec 1 `
            -UseBasicParsing
        if ($response.StatusCode -eq 200) {
            $apiReady = $true
            break
        }
    }
    catch {
        Start-Sleep -Milliseconds 500
    }
}
if (-not $apiReady) {
    Stop-Process -Id $backendProcess.Id -ErrorAction SilentlyContinue
    throw "DeployGuard API did not become ready. Inspect $backendErr"
}

$workerProcess = Start-Process `
    -FilePath $pythonExe `
    -ArgumentList '-m', 'app.worker', '--poll-interval', '1', '--lease-timeout', '300' `
    -WorkingDirectory $backendRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $workerOut `
    -RedirectStandardError $workerErr `
    -PassThru

$frontendProcess = Start-Process `
    -FilePath $nodeExe `
    -ArgumentList $angularCli, 'serve', '--host', '127.0.0.1', '--port', '4300' `
    -WorkingDirectory $frontendRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $frontendOut `
    -RedirectStandardError $frontendErr `
    -PassThru

Set-Content -LiteralPath (Join-Path $runtimeRoot 'backend.pid') -Value $backendProcess.Id
Set-Content -LiteralPath (Join-Path $runtimeRoot 'worker.pid') -Value $workerProcess.Id
Set-Content -LiteralPath (Join-Path $runtimeRoot 'frontend.pid') -Value $frontendProcess.Id

Write-Output "DeployGuard API: http://127.0.0.1:8100/docs"
Write-Output "DeployGuard UI:  http://127.0.0.1:4300"
Write-Output "Mode:            connected (synthetic seeding disabled)"
Write-Output "Worker:          PID $($workerProcess.Id)"
Write-Output "Logs:            $runtimeRoot"
