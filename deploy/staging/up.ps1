#!/usr/bin/env pwsh
# YiLuAn Staging - up.ps1 (D-044)
# Brings the staging mock environment up end-to-end.
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

Write-Host "==> docker compose up -d (build mocks if needed)" -ForegroundColor Cyan
docker compose -p yiluan-staging -f docker-compose.staging.yml up -d --build

Write-Host "==> waiting for backend healthcheck..." -ForegroundColor Cyan
$deadline = (Get-Date).AddSeconds(180)
while ((Get-Date) -lt $deadline) {
    $health = (docker compose -p yiluan-staging -f docker-compose.staging.yml ps --format json) 2>$null
    try {
        $resp = Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 http://127.0.0.1:18080/api/v1/ping
        if ($resp.StatusCode -eq 200) { Write-Host "backend ready: $($resp.Content)" -ForegroundColor Green; break }
    } catch { }
    Start-Sleep -Seconds 3
}

Write-Host "==> running alembic upgrade head" -ForegroundColor Cyan
docker compose -p yiluan-staging -f docker-compose.staging.yml exec -T backend-staging alembic upgrade head

Write-Host "==> seeding staging fixtures" -ForegroundColor Cyan
python seed_staging.py --base http://127.0.0.1:18080 --admin-token staging-admin-token --compose-project yiluan-staging

Write-Host "==> staging is up" -ForegroundColor Green
Write-Host "   API gateway : http://127.0.0.1:18080/api/v1/ping"
Write-Host "   Health      : http://127.0.0.1:18080/health"
Write-Host "   Readiness   : http://127.0.0.1:18080/readiness"
Write-Host "   Mock pay    : http://127.0.0.1:18080/__staging/mock-pay/health"
Write-Host "   Mock sms    : http://127.0.0.1:18080/__staging/mock-sms/health"
Write-Host ""
Write-Host "Run rehearsal: python replay/run-weekly-rehearsal.py"
Write-Host "Tear down   : ./down.ps1"
