#!/usr/bin/env pwsh
# YiLuAn 部署 - down.ps1（完整清理，含数据卷）
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

$project = "yiluan-staging"

$envFiles = @("--env-file", "env.staging")
if (Test-Path "env.staging.local") {
    $envFiles += @("--env-file", "env.staging.local")
}

$compose = @("compose", "-p", $project) + $envFiles + @("--profile", "staging", "-f", "docker-compose.yml")

Write-Host "==> docker compose down -v --remove-orphans" -ForegroundColor Cyan
docker @compose down -v --remove-orphans

Write-Host "==> torn down" -ForegroundColor Green
