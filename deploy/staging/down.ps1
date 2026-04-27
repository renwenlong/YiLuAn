#!/usr/bin/env pwsh
# YiLuAn Staging - down.ps1 (D-044)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

Write-Host "==> docker compose down -v (full cleanup)" -ForegroundColor Cyan
docker compose -p yiluan-staging -f docker-compose.staging.yml down -v --remove-orphans

Write-Host "==> staging torn down" -ForegroundColor Green
