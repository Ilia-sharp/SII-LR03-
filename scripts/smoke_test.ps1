$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

$python = Join-Path (Get-Location) ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "Сначала запусти scripts\run.ps1, чтобы создать окружение." -ForegroundColor Yellow
    exit 1
}

$base = "http://127.0.0.1:8000"
$health = Invoke-RestMethod "$base/health"
if ($health.status -ne "ok") { throw "GET /health failed" }

Get-ChildItem .\samples\*.wav | ForEach-Object {
    Write-Host "Testing $($_.Name)..."
    $curl = Get-Command curl.exe -ErrorAction Stop
    $raw = & $curl.Source -sS -X POST "$base/transcribe" -F "file=@$($_.FullName)"
    if ($LASTEXITCODE -ne 0) { throw "POST /transcribe failed for $($_.Name)" }
    $json = $raw | ConvertFrom-Json
    if ($json.language -ne "ru") { throw "Wrong language in $($_.Name)" }
    if ($json.scenario_id -ne "car_wash") { throw "Wrong scenario_id in $($_.Name)" }
    Write-Host "  text: $($json.text)"
    Write-Host "  keywords: $((($json.keywords_found | ForEach-Object { $_.keyword }) -join ', '))"
}

Write-Host "Smoke-test PASSED" -ForegroundColor Green
