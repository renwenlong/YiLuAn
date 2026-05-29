#!/usr/bin/env bash
# YiLuAn 部署 - up.sh
# 通用 docker-compose.yml + env.<环境> 模式。默认起 staging。
#
# 用法：
#   ./up.sh                 # staging（自动叠加 env.staging.local 若存在）
#
set -euo pipefail
cd "$(dirname "$0")"

PROJECT="yiluan-staging"
PROFILE="staging"

ENV_FILES=( --env-file env.staging )
if [ -f env.staging.local ]; then
  ENV_FILES+=( --env-file env.staging.local )
  echo "   (loading env.staging.local for local secret overrides)"
fi

COMPOSE=( docker compose -p "$PROJECT" "${ENV_FILES[@]}" --profile "$PROFILE" -f docker-compose.yml )

echo "==> docker compose up -d --build"
"${COMPOSE[@]}" up -d --build

echo "==> waiting for backend healthcheck..."
deadline=$(( $(date +%s) + 180 ))
while [ "$(date +%s)" -lt "$deadline" ]; do
  if curl -fsS --max-time 3 http://127.0.0.1:18080/api/v1/ping >/dev/null 2>&1; then
    echo "backend ready"
    break
  fi
  sleep 3
done

echo "==> running alembic upgrade head"
"${COMPOSE[@]}" exec -T backend alembic upgrade head

echo "==> seeding staging fixtures"
python3 staging/seed_staging.py --base http://127.0.0.1:18080 --admin-token staging-admin-token --compose-project "$PROJECT"

echo "==> staging is up"
echo "   API gateway : http://127.0.0.1:18080/api/v1/ping"
echo "   Health      : http://127.0.0.1:18080/health"
echo "   Readiness   : http://127.0.0.1:18080/readiness"
echo "   Admin H5    : http://127.0.0.1:18080/admin/"
echo "   Mock pay    : http://127.0.0.1:18080/__staging/mock-pay/health"
echo "   Mock sms    : http://127.0.0.1:18080/__staging/mock-sms/health"
echo ""
echo "Run rehearsal: python3 staging/replay/run-weekly-rehearsal.py"
echo "Tear down   : ./down.sh"
