#!/usr/bin/env bash
# YiLuAn 部署 - up.sh
# 通用 docker-compose.yml + env.<环境> 模式。
#
# 用法：
#   ./up.sh            # staging（默认，自动叠加 env.staging.local 若存在）
#   ./up.sh dev        # dev 轻量本地栈（仅 db+redis，后端 uvicorn 裸跑）
#   ./up.sh staging    # 同默认
#
set -euo pipefail
cd "$(dirname "$0")"

ENVNAME="${1:-staging}"

# ---- dev：独立轻量栈（dev/docker-compose.yml，仅 db+redis；后端裸跑）----
if [ "$ENVNAME" = "dev" ]; then
  cd dev
  if [ ! -f env.dev ]; then
    echo "未找到 dev/env.dev，从 env.dev.example 复制一份默认值。" >&2
    cp env.dev.example env.dev
  fi
  echo "==> docker compose up -d (env=dev, db+redis only)"
  docker compose -p yiluan-dev --env-file env.dev -f docker-compose.yml up -d
  echo "==> dev infra is up（后端请在 backend/ 下用 uvicorn 裸跑）"
  echo "   Postgres : 127.0.0.1:5433 (DATABASE_URL=...@127.0.0.1:5433/yiluan)"
  echo "   Redis    : 127.0.0.1:6380 (REDIS_URL=redis://127.0.0.1:6380/0)"
  echo ""
  echo "Tear down : ./down.sh dev"
  exit 0
fi

case "$ENVNAME" in
  staging)
    PROJECT="yiluan-staging"
    PROFILE="staging"
    ;;
  production)
    echo "production 部署请走专用流程（确认 env.production + 域名/证书），本脚本暂不直接拉起 production。" >&2
    exit 2
    ;;
  *)
    echo "未知环境: $ENVNAME（支持 dev|staging）" >&2
    exit 2
    ;;
esac

# 解析 env 文件：env.<环境> + 可选 env.<环境>.local 叠加
if [ ! -f "env.${ENVNAME}" ]; then
  echo "缺少 env.${ENVNAME}，请先从 env.${ENVNAME}.example 复制。" >&2
  exit 2
fi

ENV_FILES=( --env-file "env.${ENVNAME}" )
if [ -f "env.${ENVNAME}.local" ]; then
  ENV_FILES+=( --env-file "env.${ENVNAME}.local" )
  echo "   (loading env.${ENVNAME}.local for local secret overrides)"
fi

COMPOSE=( docker compose -p "$PROJECT" "${ENV_FILES[@]}" --profile "$PROFILE" -f docker-compose.yml )

echo "==> docker compose up -d --build (env=${ENVNAME}, profile=${PROFILE})"
"${COMPOSE[@]}" up -d --build

# ---- staging 流程 ----
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
