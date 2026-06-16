#!/usr/bin/env bash
# YiLuAn 部署 - down.sh（完整清理，含数据卷）
#
# 用法：
#   ./down.sh          # staging（默认）
#   ./down.sh canary   # S2-OPS-013 canary 栈
#
set -euo pipefail
cd "$(dirname "$0")"

ENVNAME="${1:-staging}"

case "$ENVNAME" in
  staging) PROJECT="yiluan-staging"; PROFILE="staging" ;;
  canary)  PROJECT="yiluan-canary";  PROFILE="canary" ;;
  *) echo "未知环境: $ENVNAME（支持 staging|canary）" >&2; exit 2 ;;
esac

if [ "$ENVNAME" = "canary" ]; then
  ENV_FILES=( --env-file "env.staging" --env-file "env.canary" )
  if [ -f "env.canary.local" ]; then
    ENV_FILES+=( --env-file "env.canary.local" )
  fi
else
  ENV_FILES=( --env-file "env.${ENVNAME}" )
  if [ -f "env.${ENVNAME}.local" ]; then
    ENV_FILES+=( --env-file "env.${ENVNAME}.local" )
  fi
fi

echo "==> docker compose down -v --remove-orphans (env=${ENVNAME})"
docker compose -p "$PROJECT" "${ENV_FILES[@]}" --profile "$PROFILE" -f docker-compose.yml down -v --remove-orphans

echo "==> torn down"
