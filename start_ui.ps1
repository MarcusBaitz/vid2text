param(
    [int]$Port = $(if ($env:VID2TEXT_UI_PORT) { [int]$env:VID2TEXT_UI_PORT } else { 7860 }),
    [string]$HostName = $(if ($env:VID2TEXT_UI_HOST) { $env:VID2TEXT_UI_HOST } else { "127.0.0.1" }),
    [switch]$NoBrowser,
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
trap {
    Write-Host ""
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$env:PYTHONUTF8 = "1"

$runArgs = @("-Diagnose")
if ($SkipInstall) {
    $runArgs += "-SkipInstall"
}

Write-Host ""
Write-Host "==> Runtime wird vorbereitet" -ForegroundColor Cyan
& powershell -ExecutionPolicy Bypass -File (Join-Path $Root "run.ps1") @runArgs
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$pythonExe = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    throw "Python in .venv wurde nicht gefunden: $pythonExe"
}

$uiArgs = @((Join-Path $Root "web_app.py"), "--host", $HostName, "--port", "$Port")
if ($NoBrowser) {
    $uiArgs += "--no-browser"
}

Write-Host ""
Write-Host "==> UI startet auf http://$HostName`:$Port" -ForegroundColor Cyan
& $pythonExe @uiArgs
exit $LASTEXITCODE
