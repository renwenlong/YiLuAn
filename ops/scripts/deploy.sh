#!/usr/bin/env bash
# deploy.sh — YiLuAn 部署脚本骨架(canary / rollback)
#
# 当前阶段:**纯 docker-compose mock**,真生产上线前需把每个 TODO(prod) 替换为
# 真实的 nginx reload + ACR pull + k8s/Container Apps 切流命令。
#
# 用法:
#   bash ops/scripts/deploy.sh --canary --tag v1.5.0
#   bash ops/scripts/deploy.sh --canary --stage 5         # 只走 5% stage
#   bash ops/scripts/deploy.sh --rollback                 # 立即流量回切 stable
#   bash ops/scripts/deploy.sh --rollback --code v1.4.2   # 含代码回滚到 v1.4.2
#
# 设计目标:
#   - 单脚本入口,统一所有 ops 操作
#   - 与 RUNBOOK_ROLLBACK.md 场景 A/B 一一对应
#   - 与 ADR-0028 的 stage 序列(5/25/50/100)一致
#   - 干跑安全(mock 模式不触碰任何真实服务)
#
# 真生产 TODO(放 follow-up sprint):
#   T1. 替换 mock_nginx_apply 为真实 ssh + nginx -t + nginx -s reload
#   T2. 加 ACR docker pull / docker compose up 真实命令
#   T3. 加 Prometheus 自动门禁查询(stage 观察期内 5xx/p99)
#   T4. 加企业微信通报集成(复用 ops/alertmanager/wechat-work-webhook.py 的 send 函数)
#   T5. 接 secrets manager(KMS / Key Vault)做 PREV_TAG 自动发现

set -uo pipefail

ACTION=""
TAG=""
PREV_TAG=""
STAGE=""
ROLLBACK_CODE=0
DRY_RUN=1   # 默认 dry-run,真生产需显式 --no-dry-run

while [ $# -gt 0 ]; do
  case "$1" in
    --canary)        ACTION="canary" ;;
    --rollback)      ACTION="rollback" ;;
    --tag)           shift; TAG="$1" ;;
    --prev-tag)      shift; PREV_TAG="$1" ;;
    --stage)         shift; STAGE="$1" ;;
    --code)          ROLLBACK_CODE=1; shift; PREV_TAG="$1" ;;
    --no-dry-run)    DRY_RUN=0 ;;
    --help|-h)
      sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 2
      ;;
  esac
  shift
done

ts() { date '+%Y-%m-%d %H:%M:%S'; }
log()  { printf '[%s] %s\n' "$(ts)" "$*"; }
ok()   { printf '[%s] \033[32m[OK]\033[0m %s\n' "$(ts)" "$*"; }
warn() { printf '[%s] \033[33m[WARN]\033[0m %s\n' "$(ts)" "$*"; }
fail() { printf '[%s] \033[31m[FAIL]\033[0m %s\n' "$(ts)" "$*"; }

mock_nginx_apply() {
  local pct="$1"
  if [ "$DRY_RUN" -eq 1 ]; then
    log "[mock] nginx split_clients backend_new=${pct}% / backend_stable=$((100-pct))%"
    log "[mock] nginx -t           => syntax OK"
    log "[mock] nginx -s reload    => reloaded in 0.3s"
  else
    fail "TODO(prod): 替换为真实 ssh ops@nginx-prod-01 + sed + nginx -t + nginx -s reload"
    return 1
  fi
}

mock_observe() {
  local pct="$1"
  local seconds="${2:-3}"
  log "Observing stage ${pct}% for ${seconds}s (real: 1800s) ..."
  sleep "$seconds"
  ok "Stage ${pct}% observation passed (mock)"
}

mock_pull_image() {
  local tag="$1"
  if [ "$DRY_RUN" -eq 1 ]; then
    log "[mock] docker pull registry.example.com/yiluan/backend:${tag}"
    log "[mock] docker compose up -d --no-deps backend_new (rolling)"
  else
    fail "TODO(prod): 替换为真实 docker pull + compose up"
    return 1
  fi
}

# ---------------------------------------------------------------------------
# Canary
# ---------------------------------------------------------------------------
do_canary() {
  if [ -z "$TAG" ]; then fail "--canary 需要 --tag"; exit 2; fi
  log "=== CANARY DEPLOY tag=$TAG dry_run=$DRY_RUN ==="

  log "Step 1/5: pull 新镜像"
  mock_pull_image "$TAG" || exit 3

  if [ -n "$STAGE" ]; then
    STAGES=("$STAGE")
  else
    STAGES=(5 25 50 100)
  fi

  for s in "${STAGES[@]}"; do
    log "--- Stage ${s}% canary -> backend_new ---"
    mock_nginx_apply "$s" || exit 4
    mock_observe "$s" 2
    # TODO(prod): 此处查询 Prometheus, 5xx > 1% / 2min 自动调用 do_rollback
  done

  ok "Canary 完成,已 100% 切到 $TAG"
  log "[NOTIFY-WECHAT] [DEPLOY-DONE] $TAG @ 100%, 进入 24h 观察窗口"
}

# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------
do_rollback() {
  log "=== ROLLBACK code_rollback=$ROLLBACK_CODE prev_tag=$PREV_TAG dry_run=$DRY_RUN ==="

  log "Step 1: 流量层切回 backend_stable (场景 A)"
  mock_nginx_apply 0 || exit 4

  if [ "$ROLLBACK_CODE" -eq 1 ]; then
    if [ -z "$PREV_TAG" ]; then fail "--code 需要指定 PREV_TAG"; exit 2; fi
    log "Step 2: 代码层回滚到 $PREV_TAG (场景 B)"
    mock_pull_image "$PREV_TAG" || exit 3
  fi

  ok "Rollback 完成"
  log "[NOTIFY-WECHAT] [ROLLBACK] 流量已切回 stable; code_rollback=$ROLLBACK_CODE; prev_tag=$PREV_TAG"
}

case "$ACTION" in
  canary)   do_canary ;;
  rollback) do_rollback ;;
  *) echo "用法: $0 [--canary --tag <T>] | [--rollback [--code <PREV>]]" >&2; exit 2 ;;
esac
