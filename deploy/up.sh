#!/usr/bin/env bash
# YiLuAn 部署 - up.sh
# 通用 docker-compose.yml + env.<环境> 模式。
#
# 用法：
#   ./up.sh            # staging（默认，自动叠加 env.staging.local 若存在）
#   ./up.sh staging    # 同默认
#   ./up.sh canary     # S2-OPS-013: canary mock 通道独立一套容器 (错开 host port + 独立 db yiluan_canary)
#                     # 与 staging 同时运行互不干扰，需 env.canary[.local]。
#
set -euo pipefail
cd "$(dirname "$0")"

ENVNAME="${1:-staging}"

case "$ENVNAME" in
  staging)
    PROJECT="yiluan-staging"
    PROFILE="staging"
    ;;
  canary)
    # S2-OPS-013 帝君拍: wxpay 3 物料不申请,canary 走 mock 链路独立起一套
    # 与 staging 互不干扰 (独立 project name -> 独立 volume; env.canary 错开主机 port)
    PROJECT="yiluan-canary"
    PROFILE="canary"
    ;;
  production)
    echo "production 部署请走专用流程（确认 env.production + 域名/证书），本脚本暂不直接拉起 production。" >&2
    exit 2
    ;;
  *)
    echo "未知环境: $ENVNAME（支持 staging|canary）" >&2
    exit 2
    ;;
esac

# 解析 env 文件：env.<环境> + 可选 env.<环境>.local 叠加
if [ ! -f "env.${ENVNAME}" ]; then
  echo "缺少 env.${ENVNAME}，请先从 env.${ENVNAME}.example 复制。" >&2
  exit 2
fi

# S2-OPS-013 canary: env.canary 依赖 env.staging 提供公共变量 (POSTGRES_USER/JWT_SECRET_KEY 等)
# 如帝君未提供 env.canary.local 仅走 Phase 1 mock会在 ENV_FILES 后面叠加覆盖优先级递增
if [ "$ENVNAME" = "canary" ]; then
  if [ ! -f "env.staging" ]; then
    echo "canary 依赖 env.staging 提供公共变量 (POSTGRES_USER/JWT_SECRET_KEY 等)请先准备 env.staging。" >&2
    exit 2
  fi
  ENV_FILES=( --env-file "env.staging" --env-file "env.canary" )
  if [ -f "env.canary.local" ]; then
    ENV_FILES+=( --env-file "env.canary.local" )
    echo "   (loading env.canary.local for canary secret overrides)"
  fi
else
  ENV_FILES=( --env-file "env.${ENVNAME}" )
  if [ -f "env.${ENVNAME}.local" ]; then
    ENV_FILES+=( --env-file "env.${ENVNAME}.local" )
    echo "   (loading env.${ENVNAME}.local for local secret overrides)"
  fi
fi

COMPOSE=( docker compose -p "$PROJECT" "${ENV_FILES[@]}" --profile "$PROFILE" -f docker-compose.yml )

echo "==> docker compose up -d --build (env=${ENVNAME}, profile=${PROFILE})"
"${COMPOSE[@]}" up -d --build

# ---- staging / canary 流程 ----
if [ "$ENVNAME" = "canary" ]; then
  CANARY_PORT="${NGINX_HOST_PORT:-18090}"
  HEALTH_URL="http://127.0.0.1:${CANARY_PORT}/api/v1/ping"
else
  HEALTH_URL="http://127.0.0.1:18080/api/v1/ping"
fi

echo "==> waiting for backend healthcheck..."
deadline=$(( $(date +%s) + 180 ))
while [ "$(date +%s)" -lt "$deadline" ]; do
  if curl -fsS --max-time 3 "$HEALTH_URL" >/dev/null 2>&1; then
    echo "backend ready"
    break
  fi
  sleep 3
done

echo "==> running alembic upgrade head"
"${COMPOSE[@]}" exec -T backend alembic upgrade head

if [ "$ENVNAME" = "staging" ]; then
  echo "==> seeding staging fixtures"
  python3 staging/seed_staging.py --base http://127.0.0.1:18080 --admin-token staging-admin-token --compose-project "$PROJECT"

  echo "==> staging is up"
  echo "   API gateway : http://127.0.0.1:18080/api/v1/ping"
  echo "   Health      : http://127.0.0.1:18080/health"
  echo "   Readiness   : http://127.0.0.1:18080/readiness"
  echo "   Admin H5    : http://127.0.0.1:18080/admin/"
  echo "   Admin v2    : http://127.0.0.1:18080/admin-v2/  (需预先 cd admin-v2 + npm install + npm run build)"
  echo "   Mock pay    : http://127.0.0.1:18080/__staging/mock-pay/health"
  echo "   Mock sms    : http://127.0.0.1:18080/__staging/mock-sms/health"
  echo "   Prometheus  : http://127.0.0.1:9090"
  echo "   Alertmanager: http://127.0.0.1:9093"
  echo "   Grafana     : http://127.0.0.1:13000  (admin / staging-grafana-not-for-prod)"
  echo ""
  echo "Run rehearsal: python3 staging/replay/run-weekly-rehearsal.py"
  echo "Tear down   : ./down.sh"
else
  # canary 不 seed staging fixtures（独立 db，需要时单独跳 seed_staging.py --base canary）
  echo "==> canary is up (mock 链路, S2-OPS-013, 帝君拍 Phase 1)"
  CANARY_PROM="${PROM_HOST_PORT:-9091}"
  CANARY_AM="${AM_HOST_PORT:-9094}"
  CANARY_GRAF="${GRAFANA_HOST_PORT:-13001}"
  echo "   API gateway : http://127.0.0.1:${CANARY_PORT}/api/v1/ping"
  echo "   Health      : http://127.0.0.1:${CANARY_PORT}/health"
  echo "   Readiness   : http://127.0.0.1:${CANARY_PORT}/readiness"
  echo "   Mock pay    : http://127.0.0.1:${CANARY_PORT}/__staging/mock-pay/health"
  echo "   Mock sms    : http://127.0.0.1:${CANARY_PORT}/__staging/mock-sms/health"
  echo "   Prometheus  : http://127.0.0.1:${CANARY_PROM}"
  echo "   Alertmanager: http://127.0.0.1:${CANARY_AM}"
  echo "   Grafana     : http://127.0.0.1:${CANARY_GRAF}  (admin / staging-grafana-not-for-prod)"
  echo ""
  echo "Tear down   : ./down.sh canary"
fi
