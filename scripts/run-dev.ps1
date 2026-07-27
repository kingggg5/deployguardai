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

$frontendProcess = Start-Process `
    -FilePath $nodeExe `
    -ArgumentList $angularCli, 'serve', '--host', '127.0.0.1', '--port', '4300' `
    -WorkingDirectory $frontendRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $frontendOut `
    -RedirectStandardError $frontendErr `
    -PassThru

Set-Content -LiteralPath (Join-Path $runtimeRoot 'backend.pid') -Value $backendProcess.Id
Set-Content -LiteralPath (Join-Path $runtimeRoot 'frontend.pid') -Value $frontendProcess.Id

Write-Output "DeployGuard API: http://127.0.0.1:8100/docs"
Write-Output "DeployGuard UI:  http://127.0.0.1:4300"
Write-Output "Logs:            $runtimeRoot"
