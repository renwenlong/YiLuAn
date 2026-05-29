#!/usr/bin/env pwsh
# YiLuAn 部署 - up.ps1
# 通用 docker-compose.yml + env.<环境> 模式。默认起 staging。
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

$project = "yiluan-staging"
$profile = "staging"

$envFiles = @("--env-file", "env.staging")
if (Test-Path "env.staging.local") {
    $envFiles += @("--env-file", "env.staging.local")
    Write-Host "   (loading env.staging.local for local secret overrides)" -ForegroundColor DarkGray
}

$compose = @("compose", "-p", $project) + $envFiles + @("--profile", $profile, "-f", "docker-compose.yml")

Write-Host "==> docker compose up -d --build" -ForegroundColor Cyan
docker @compose up -d --build

Write-Host "==> waiting for backend healthcheck..." -ForegroundColor Cyan
$deadline = (Get-Date).AddSeconds(180)
while ((Get-Date) -lt $deadline) {
    try {
        $resp = Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 http://127.0.0.1:18080/api/v1/ping
        if ($resp.StatusCode -eq 200) { Write-Host "backend ready: $($resp.Content)" -ForegroundColor Green; break }
    } catch { }
    Start-Sleep -Seconds 3
}

Write-Host "==> running alembic upgrade head" -ForegroundColor Cyan
docker @compose exec -T backend alembic upgrade head

Write-Host "==> seeding staging fixtures" -ForegroundColor Cyan
python staging/seed_staging.py --base http://127.0.0.1:18080 --admin-token staging-admin-token --compose-project $project

Write-Host "==> staging is up" -ForegroundColor Green
Write-Host "   API gateway : http://127.0.0.1:18080/api/v1/ping"
Write-Host "   Health      : http://127.0.0.1:18080/health"
Write-Host "   Readiness   : http://127.0.0.1:18080/readiness"
Write-Host "   Admin H5    : http://127.0.0.1:18080/admin/"
Write-Host "   Mock pay    : http://127.0.0.1:18080/__staging/mock-pay/health"
Write-Host "   Mock sms    : http://127.0.0.1:18080/__staging/mock-sms/health"
Write-Host ""
Write-Host "Run rehearsal: python staging/replay/run-weekly-rehearsal.py"
Write-Host "Tear down   : ./down.ps1"
