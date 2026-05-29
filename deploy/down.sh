#!/usr/bin/env bash
# YiLuAn 部署 - down.sh（完整清理，含数据卷）
set -euo pipefail
cd "$(dirname "$0")"

PROJECT="yiluan-staging"

ENV_FILES=( --env-file env.staging )
if [ -f env.staging.local ]; then
  ENV_FILES+=( --env-file env.staging.local )
fi

echo "==> docker compose down -v --remove-orphans"
docker compose -p "$PROJECT" "${ENV_FILES[@]}" --profile staging -f docker-compose.yml down -v --remove-orphans

echo "==> torn down"
