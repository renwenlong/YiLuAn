#!/usr/bin/env bash
# YiLuAn Staging - down.sh (D-044)
set -euo pipefail
cd "$(dirname "$0")"

echo "==> docker compose down -v (full cleanup)"
docker compose -p yiluan-staging -f docker-compose.staging.yml down -v --remove-orphans

echo "==> staging torn down"
