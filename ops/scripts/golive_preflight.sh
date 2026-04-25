#!/usr/bin/env bash
# golive_preflight.sh — YiLuAn GoLive 预发布检查一键脚本
#
# 目的:把 docs/runbook-go-live.md §0 通用前置 + §B-01..B-05 中可自动化的预检
# 全部汇总到一个脚本,本地或 staging 运行,输出每项 ✅ / ⚠️ / 🛑。
#
# 默认指向本地 dry-run 实例:
#   - PG    127.0.0.1:55437  (postgres/postgres/yiluan)
#   - Redis 127.0.0.1:56379
#   - API   127.0.0.1:8765   (uvicorn,需要外部已启动 或 --start-api)
#
# 用法:
#   bash ops/scripts/golive_preflight.sh
#   bash ops/scripts/golive_preflight.sh --no-api      # 跳过 readiness HTTP 检查
#   bash ops/scripts/golive_preflight.sh --pg-port 55437 --redis-port 56379
#   PG_PORT=55437 REDIS_PORT=56379 API_URL=http://localhost:8765 bash ops/scripts/golive_preflight.sh
#
# 退出码:
#   0   全部 ✅
#   1   至少一项 ⚠️ 但无 🛑
#   2   至少一项 🛑(阻塞,不允许上线)

set -uo pipefail

PG_PORT="${PG_PORT:-55437}"
REDIS_PORT="${REDIS_PORT:-56379}"
API_URL="${API_URL:-http://127.0.0.1:8765}"
SKIP_API=0
SKIP_MIGRATIONS=0

for arg in "$@"; do
  case "$arg" in
    --no-api)         SKIP_API=1 ;;
    --no-migrations)  SKIP_MIGRATIONS=1 ;;
    --pg-port)        shift; PG_PORT="$1" ;;
    --redis-port)     shift; REDIS_PORT="$1" ;;
    --help|-h)
      sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
  esac
  shift || true
done

REPORT=()
WARN=0
BLOCK=0

ts() { date '+%Y-%m-%d %H:%M:%S'; }
log()   { printf '[%s] %s\n' "$(ts)" "$*"; }
ok()    { printf '[%s] \033[32m[ OK ]\033[0m %s\n' "$(ts)" "$*"; REPORT+=("OK   | $*"); }
warn()  { printf '[%s] \033[33m[WARN]\033[0m %s\n' "$(ts)" "$*"; REPORT+=("WARN | $*"); WARN=$((WARN+1)); }
block() { printf '[%s] \033[31m[BLK ]\033[0m %s\n' "$(ts)" "$*"; REPORT+=("BLK  | $*"); BLOCK=$((BLOCK+1)); }

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

# ---------------------------------------------------------------------------
# 0. 工具/前置存在性
# ---------------------------------------------------------------------------
log "=== 0. 工具/前置 ==="
for cmd in docker python3 curl jq; do
  if command -v "$cmd" >/dev/null 2>&1; then
    ok "命令 $cmd 可用"
  else
    if [ "$cmd" = "python3" ] && command -v python >/dev/null 2>&1; then
      ok "命令 python (fallback for python3) 可用"
    elif [ "$cmd" = "jq" ]; then
      warn "命令 jq 不可用(部分校验将简化为字符串匹配)"
    else
      block "命令 $cmd 不可用"
    fi
  fi
done

# ---------------------------------------------------------------------------
# 1. 本地依赖容器
# ---------------------------------------------------------------------------
log "=== 1. 本地依赖容器 (PG=$PG_PORT, Redis=$REDIS_PORT) ==="
if (echo > "/dev/tcp/127.0.0.1/$PG_PORT") 2>/dev/null; then
  ok "PG 端口 $PG_PORT 可达"
else
  block "PG 端口 $PG_PORT 不可达 — 请先 docker run -d -p $PG_PORT:5432 postgres:15-alpine"
fi
if (echo > "/dev/tcp/127.0.0.1/$REDIS_PORT") 2>/dev/null; then
  ok "Redis 端口 $REDIS_PORT 可达"
else
  block "Redis 端口 $REDIS_PORT 不可达 — 请先 docker run -d -p $REDIS_PORT:6379 redis:7-alpine"
fi

# ---------------------------------------------------------------------------
# 2. 配置一致性 (.env.example vs app/config.py)
# ---------------------------------------------------------------------------
log "=== 2. 配置一致性 ==="
ENV_EXAMPLE="backend/.env.example"
CONFIG_PY="backend/app/config.py"
if [ ! -f "$ENV_EXAMPLE" ]; then block ".env.example 缺失"; fi
if [ ! -f "$CONFIG_PY" ]; then block "app/config.py 缺失"; fi

# 抽几个关键 KEY 名,确保 runbook 引用的与代码一致
for key in WECHAT_PAY_MCH_ID WECHAT_PAY_API_KEY_V3 WECHAT_PAY_PRIVATE_KEY_PATH \
           ALIYUN_SMS_ACCESS_KEY_ID ALIYUN_SMS_ACCESS_KEY_SECRET \
           ALIYUN_SMS_SIGN_NAME ALIYUN_SMS_TEMPLATE_CODE \
           DATABASE_URL REDIS_URL JWT_SECRET_KEY; do
  if grep -q "^${key}=" "$ENV_EXAMPLE" 2>/dev/null; then
    # 转小写后在 config.py 找
    lc="$(echo "$key" | tr '[:upper:]' '[:lower:]')"
    if grep -q -i "^\s*${lc}\s*[:=]" "$CONFIG_PY" 2>/dev/null; then
      ok "ENV $key ↔ config.${lc} 一致"
    else
      warn "ENV $key 未在 config.py 找到对应字段"
    fi
  else
    warn "ENV $key 不在 .env.example 中"
  fi
done

# 反向告警:runbook 里出现但代码不支持的旧/错误 key
for bad_key in WECHATPAY_MCH_ID WECHATPAY_APIV3_KEY ALIYUN_SMS_AK_ID \
               ALIYUN_SMS_TEMPLATE_OTP; do
  if grep -q "^${bad_key}=" "$ENV_EXAMPLE" 2>/dev/null; then
    block "ENV $bad_key 在 .env.example 出现,但代码不支持"
  fi
done

# ---------------------------------------------------------------------------
# 3. Alembic 迁移可逆性(三轮 upgrade/downgrade)
# ---------------------------------------------------------------------------
if [ "$SKIP_MIGRATIONS" -eq 0 ]; then
  log "=== 3. Alembic 三轮 upgrade↔downgrade ==="
  cd backend
  PYTHON="python3"
  command -v python3 >/dev/null 2>&1 || PYTHON="python"
  if [ ! -d ".venv-dryrun" ]; then
    log "创建 .venv-dryrun ..."
    "$PYTHON" -m venv .venv-dryrun
    ./.venv-dryrun/bin/pip install --quiet -r requirements.txt 2>/dev/null \
      || ./.venv-dryrun/Scripts/pip install --quiet -r requirements.txt
  fi
  if [ -x ./.venv-dryrun/bin/python ]; then
    PY=./.venv-dryrun/bin/python
  else
    PY=./.venv-dryrun/Scripts/python
  fi

  export ALEMBIC_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:${PG_PORT}/yiluan"
  export DATABASE_URL="$ALEMBIC_DATABASE_URL"
  export REDIS_URL="redis://localhost:${REDIS_PORT}/0"

  for i in 1 2 3; do
    if "$PY" -m alembic upgrade head >/tmp/alembic_up_$i.log 2>&1; then
      ok "alembic upgrade head (round $i)"
    else
      block "alembic upgrade head (round $i) failed — see /tmp/alembic_up_$i.log"
      break
    fi
    if [ "$i" -lt 3 ]; then
      if "$PY" -m alembic downgrade base >/tmp/alembic_down_$i.log 2>&1; then
        ok "alembic downgrade base (round $i)"
      else
        block "alembic downgrade base (round $i) failed"
        break
      fi
    fi
  done

  CURRENT="$("$PY" -m alembic current 2>&1 | tail -1 | awk '{print $1}')"
  if [ -n "$CURRENT" ] && [ "$CURRENT" != "INFO" ]; then
    ok "alembic current head = $CURRENT"
  else
    warn "alembic current 解析失败"
  fi
  cd "$REPO_ROOT"
else
  warn "Alembic 检查被 --no-migrations 跳过"
fi

# ---------------------------------------------------------------------------
# 4. /readiness 5 项依赖
# ---------------------------------------------------------------------------
if [ "$SKIP_API" -eq 0 ]; then
  log "=== 4. /readiness 检查 ==="
  CODE="$(curl -s -o /tmp/readiness.json -w '%{http_code}' "$API_URL/readiness" || echo 000)"
  if [ "$CODE" = "200" ]; then
    ok "/readiness HTTP 200"
    if command -v jq >/dev/null 2>&1; then
      for k in db redis alembic payment sms; do
        st="$(jq -r ".checks.$k.status" /tmp/readiness.json)"
        case "$st" in
          ok|skipped) ok "/readiness checks.$k = $st" ;;
          *)          warn "/readiness checks.$k = $st" ;;
        esac
      done
    fi
  else
    block "/readiness HTTP $CODE — API 未启动?(可用 --no-api 跳过)"
  fi
else
  warn "/readiness 检查被 --no-api 跳过"
fi

# ---------------------------------------------------------------------------
# 5. Alertmanager compose 校验(干跑,不真启动)
# ---------------------------------------------------------------------------
log "=== 5. Alertmanager compose 配置干跑 ==="
if docker compose -f docker-compose.alertmanager.yml config >/tmp/alertmanager_config.log 2>&1; then
  ok "docker-compose.alertmanager.yml 配置有效"
else
  warn "docker-compose.alertmanager.yml config 失败 — 见 /tmp/alertmanager_config.log"
fi

# ---------------------------------------------------------------------------
# 6. 关键 runbook / ADR 文档存在
# ---------------------------------------------------------------------------
log "=== 6. 必备文档 ==="
for f in docs/runbook-go-live.md docs/RUNBOOK_ROLLBACK.md \
         docs/decisions/ADR-0028-canary-release-and-rollback.md \
         docs/MIGRATION_REVERSIBILITY_REPORT.md \
         docs/ops/INCIDENT_PLAYBOOK.md; do
  if [ -f "$f" ]; then ok "存在 $f"; else warn "缺少 $f"; fi
done

# ---------------------------------------------------------------------------
# 7. canary_drill.sh 行尾(LF 必需)
# ---------------------------------------------------------------------------
log "=== 7. ops/scripts/*.sh 行尾检查 ==="
for sh in ops/scripts/canary_drill.sh ops/scripts/metrics_baseline.sh \
          ops/scripts/golive_preflight.sh ops/scripts/deploy.sh; do
  [ -f "$sh" ] || continue
  if grep -qU $'\r' "$sh"; then
    warn "$sh 含 CRLF 行尾,在 Linux bash 上可能直接报错"
  else
    ok "$sh LF 行尾"
  fi
done

# ---------------------------------------------------------------------------
# 汇总
# ---------------------------------------------------------------------------
log "=========================================="
log "GoLive Preflight Summary"
log "  OK / WARN / BLOCK = $((${#REPORT[@]}-WARN-BLOCK)) / $WARN / $BLOCK"
log "=========================================="
printf '%s\n' "${REPORT[@]}"

if [ "$BLOCK" -gt 0 ]; then
  log "🛑 阻塞项存在,**不允许上线**"
  exit 2
elif [ "$WARN" -gt 0 ]; then
  log "⚠️ 有警告项,需 PM/Arch 评估后决定是否上线"
  exit 1
else
  log "✅ 全部通过,可进入灰度发布"
  exit 0
fi
