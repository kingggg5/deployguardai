param(
    [switch]$SkipInstall
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$backendRoot = Join-Path $projectRoot 'backend'
$controlPlaneRoot = Join-Path $projectRoot 'control-plane'
$frontendRoot = Join-Path $projectRoot 'frontend'
$runtimeRoot = Join-Path $projectRoot '.runtime'
$venvRoot = Join-Path $backendRoot '.venv'
$pythonExe = Join-Path $venvRoot 'Scripts\python.exe'
$nodeExe = (Get-Command node.exe -ErrorAction Stop).Source
$dotnetExe = (Get-Command dotnet.exe -ErrorAction Stop).Source
$angularCli = Join-Path $frontendRoot 'node_modules\@angular\cli\bin\ng.js'
$controlPlaneProject = Join-Path $controlPlaneRoot 'src\DeployGuard.ControlPlane\DeployGuard.ControlPlane.csproj'

New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null

foreach ($name in @('backend', 'python-api', 'api', 'worker', 'frontend')) {
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
    & $dotnetExe restore (Join-Path $controlPlaneRoot 'DeployGuard.ControlPlane.slnx') --nologo
    if (-not (Test-Path -LiteralPath (Join-Path $frontendRoot 'node_modules'))) {
        npm --prefix $frontendRoot install
    }
}

$pythonApiOut = Join-Path $runtimeRoot 'python-api.stdout.log'
$pythonApiErr = Join-Path $runtimeRoot 'python-api.stderr.log'
$apiOut = Join-Path $runtimeRoot 'api.stdout.log'
$apiErr = Join-Path $runtimeRoot 'api.stderr.log'
$workerOut = Join-Path $runtimeRoot 'worker.stdout.log'
$workerErr = Join-Path $runtimeRoot 'worker.stderr.log'
$frontendOut = Join-Path $runtimeRoot 'frontend.stdout.log'
$frontendErr = Join-Path $runtimeRoot 'frontend.stderr.log'

$pythonApiProcess = Start-Process `
    -FilePath $pythonExe `
    -ArgumentList '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8101', '--reload' `
    -WorkingDirectory $backendRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $pythonApiOut `
    -RedirectStandardError $pythonApiErr `
    -PassThru

$pythonApiReady = $false
for ($attempt = 0; $attempt -lt 60; $attempt++) {
    if ($pythonApiProcess.HasExited) {
        break
    }
    try {
        $response = Invoke-WebRequest `
            -Uri 'http://127.0.0.1:8101/api/v1/health/ready' `
            -TimeoutSec 1 `
            -UseBasicParsing
        if ($response.StatusCode -eq 200) {
            $pythonApiReady = $true
            break
        }
    }
    catch {
        Start-Sleep -Milliseconds 500
    }
}
if (-not $pythonApiReady) {
    Stop-Process -Id $pythonApiProcess.Id -ErrorAction SilentlyContinue
    throw "DeployGuard Python service did not become ready. Inspect $pythonApiErr"
}

$previousAspNetCoreUrls = $env:ASPNETCORE_URLS
$previousUpstreamBaseUrl = $env:Upstream__BaseUrl
$previousDatabaseProbe = $env:Database__ProbeEnabled
$previousDataMode = $env:DataMode
try {
    $env:ASPNETCORE_URLS = 'http://127.0.0.1:8100'
    $env:Upstream__BaseUrl = 'http://127.0.0.1:8101'
    $env:Database__ProbeEnabled = 'false'
    $env:DataMode = 'connected'
    $apiProcess = Start-Process `
        -FilePath $dotnetExe `
        -ArgumentList 'run', '--project', $controlPlaneProject, '--no-launch-profile', '--no-restore' `
        -WorkingDirectory $controlPlaneRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $apiOut `
        -RedirectStandardError $apiErr `
        -PassThru
}
finally {
    $env:ASPNETCORE_URLS = $previousAspNetCoreUrls
    $env:Upstream__BaseUrl = $previousUpstreamBaseUrl
    $env:Database__ProbeEnabled = $previousDatabaseProbe
    $env:DataMode = $previousDataMode
}

$apiReady = $false
for ($attempt = 0; $attempt -lt 60; $attempt++) {
    if ($apiProcess.HasExited) {
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
    Stop-Process -Id $apiProcess.Id -ErrorAction SilentlyContinue
    Stop-Process -Id $pythonApiProcess.Id -ErrorAction SilentlyContinue
    throw "DeployGuard .NET control plane did not become ready. Inspect $apiErr"
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

Set-Content -LiteralPath (Join-Path $runtimeRoot 'python-api.pid') -Value $pythonApiProcess.Id
Set-Content -LiteralPath (Join-Path $runtimeRoot 'api.pid') -Value $apiProcess.Id
Set-Content -LiteralPath (Join-Path $runtimeRoot 'worker.pid') -Value $workerProcess.Id
Set-Content -LiteralPath (Join-Path $runtimeRoot 'frontend.pid') -Value $frontendProcess.Id

Write-Output "DeployGuard API: http://127.0.0.1:8100/docs"
Write-Output "DeployGuard UI:  http://127.0.0.1:4300"
Write-Output "Mode:            connected (synthetic seeding disabled)"
Write-Output "Control plane:   .NET 10 (Python engine/API on 127.0.0.1:8101)"
Write-Output "Worker:          PID $($workerProcess.Id)"
Write-Output "Logs:            $runtimeRoot"
