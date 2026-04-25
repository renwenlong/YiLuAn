#!/usr/bin/env bash
# canary_drill.sh - YiLuAn 灰度发布回滚演练 (mock, 不打真流量)
#
# 用途:
#   在 staging / 本地 dev 环境 mock 一次完整的灰度发布过程, 验证:
#     1) 各 stage 切换的判定逻辑
#     2) 自动回滚条件触发判定
#     3) 通知模板格式
#   全程 *不* 修改真实 nginx / 真实 backend, 仅打印计划与判定结果。
#
# 运行:
#   bash ops/scripts/canary_drill.sh                # 走完整流程, mock 5xx 在 stage 2 飙升, 触发回滚
#   bash ops/scripts/canary_drill.sh --happy-path   # mock 一切正常, 走到 100%
#   bash ops/scripts/canary_drill.sh --readiness-fail  # mock readiness 失败触发回滚
#
# 输出: stdout + 退出码 (0 演练成功, 非 0 演练剧本断言失败)
#
# 关联: docs/decisions/ADR-0028-canary-release-and-rollback.md

set -euo pipefail

SCRIPT_NAME=$(basename "$0")
MODE="default"   # default | happy-path | readiness-fail
STAGE_OBSERVE_SECONDS=2   # 演练里压缩为 2s; 真实场景 1800s
AUTO_ROLLBACK_5XX_THRESHOLD=0.01    # 1%
AUTO_ROLLBACK_5XX_DURATION=120      # 2 min (真实)
MANUAL_ROLLBACK_SLA=300             # 5 min

for arg in "$@"; do
  case "$arg" in
    --happy-path)      MODE="happy-path" ;;
    --readiness-fail)  MODE="readiness-fail" ;;
    --help|-h)
      grep '^#' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "Unknown arg: $arg" >&2
      exit 2
      ;;
  esac
done

ts() { date '+%Y-%m-%d %H:%M:%S'; }
log()    { printf '[%s] %s\n'        "$(ts)" "$*"; }
notify() { printf '[%s] [NOTIFY-WECHAT] %s\n' "$(ts)" "$*"; }
ok()     { printf '[%s] \033[32m[OK]\033[0m   %s\n' "$(ts)" "$*"; }
warn()   { printf '[%s] \033[33m[WARN]\033[0m %s\n' "$(ts)" "$*"; }
fail()   { printf '[%s] \033[31m[FAIL]\033[0m %s\n' "$(ts)" "$*"; }

# ---------------------------------------------------------------------------
# Mock 指标产生器
# ---------------------------------------------------------------------------

mock_5xx_rate() {
  local stage_pct="$1"
  case "$MODE" in
    happy-path)        echo "0.001" ;;     # 0.1%
    readiness-fail)    echo "0.002" ;;
    default)
      # 在 stage 2 (10%) 时 mock 一次 5xx 飙升
      if [[ "$stage_pct" == "10" ]]; then
        echo "0.025"   # 2.5% > 1%
      else
        echo "0.001"
      fi
      ;;
  esac
}

mock_readiness_ok() {
  local stage_pct="$1"
  case "$MODE" in
    readiness-fail)
      # stage 1 起 readiness 就开始失败
      [[ "$stage_pct" == "1" ]] && echo "false" || echo "true"
      ;;
    *) echo "true" ;;
  esac
}

# ---------------------------------------------------------------------------
# 切流量 (mock)
# ---------------------------------------------------------------------------

apply_split_clients() {
  local pct="$1"
  log "[mock] sed nginx config: backend_new=${pct}% / backend_stable=$((100-pct))%"
  log "[mock] nginx -t           => syntax OK"
  log "[mock] nginx -s reload    => reloaded in 0.3s, no dropped connections"
}

# ---------------------------------------------------------------------------
# 阶段观察 (压缩演练)
# ---------------------------------------------------------------------------

observe_stage() {
  local pct="$1"
  log "Observing stage ${pct}% for ${STAGE_OBSERVE_SECONDS}s (real: 1800s)..."
  local elapsed=0
  while (( elapsed < STAGE_OBSERVE_SECONDS )); do
    local rate; rate=$(mock_5xx_rate "$pct")
    local ready; ready=$(mock_readiness_ok "$pct")
    log "  metrics: 5xx_rate=${rate} (threshold ${AUTO_ROLLBACK_5XX_THRESHOLD}, real-window 2min) readiness_ok=${ready}"

    # 自动回滚判定
    # 演练里把 "持续 2 min" 简化为 "本轮看到一次", 实际 watcher 是窗口聚合
    if awk -v r="$rate" -v t="$AUTO_ROLLBACK_5XX_THRESHOLD" 'BEGIN{exit !(r>t)}'; then
      warn "AUTO-ROLLBACK trigger: 5xx rate ${rate} > ${AUTO_ROLLBACK_5XX_THRESHOLD} (would persist >2min in prod)"
      return 10
    fi
    if [[ "$ready" == "false" ]]; then
      warn "AUTO-ROLLBACK trigger: ReadinessProbeFailure (P0)"
      return 11
    fi

    sleep 1
    elapsed=$((elapsed+1))
  done
  ok "Stage ${pct}% observation passed."
  return 0
}

# ---------------------------------------------------------------------------
# 回滚 (mock)
# ---------------------------------------------------------------------------

trigger_rollback() {
  local reason="$1"
  warn "Triggering ROLLBACK (Scenario A): ${reason}"
  log "[mock] sed nginx config: enable Rollback section (backend_new=0%)"
  log "[mock] nginx -t           => syntax OK"
  log "[mock] nginx -s reload    => reloaded; backend_new traffic should drain in <30s"
  notify "[ROLLBACK / Scenario A] reason=${reason} executed_by=drill mode=${MODE} sla<30s"
  ok "Mock rollback complete. Real SLA: <30s."
}

# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

log "=== YiLuAn Canary Drill (mode=${MODE}) ==="
log "Reference: docs/decisions/ADR-0028-canary-release-and-rollback.md"
log ""

# Stage 0: pre-flight
log "Stage 0: pre-flight checks (mock)"
log "  - alembic current matches expected head: OK"
log "  - backend_new healthy: OK (curl /readiness on 127.0.0.1:9001 => 200)"
log "  - backend_stable healthy: OK"
log "  - prometheus reachable: OK"
log "  - alertmanager wechat webhook configured: WARN (待 PM 提供 URL, A-2604-07)"
ok "Pre-flight done."
echo

stages=(1 10 50 100)
exit_code=0

for pct in "${stages[@]}"; do
  log "--- Stage: ${pct}% canary -> backend_new ---"
  apply_split_clients "$pct"
  set +e
  observe_stage "$pct"
  rc=$?
  set -e
  if (( rc == 10 )); then
    trigger_rollback "5xx rate exceeded ${AUTO_ROLLBACK_5XX_THRESHOLD} during stage ${pct}%"
    exit_code=1; break
  elif (( rc == 11 )); then
    trigger_rollback "ReadinessProbeFailure during stage ${pct}%"
    exit_code=1; break
  fi
  echo
done

if (( exit_code == 0 )); then
  ok "All stages passed. Canary at 100%. 24h observation window starts now (mock)."
  notify "[CANARY-DONE] 100% rollout, all 5 alerts green, observe 24h."
else
  warn "Drill ended with rollback (this is expected in default mode)."
fi

echo
log "=== Drill summary ==="
log "Mode:           ${MODE}"
log "Final exit:     ${exit_code} ($([[ $exit_code -eq 0 ]] && echo "ROLLED OUT" || echo "ROLLED BACK"))"
log "Real-world parameters:"
log "  - Stage observe window:  1800s (drill: ${STAGE_OBSERVE_SECONDS}s)"
log "  - Auto-rollback 5xx:     >${AUTO_ROLLBACK_5XX_THRESHOLD} for ${AUTO_ROLLBACK_5XX_DURATION}s"
log "  - Manual rollback SLA:   ${MANUAL_ROLLBACK_SLA}s"

# 演练剧本断言: default 模式必须触发回滚 (exit 1), happy-path 必须成功 (exit 0)
case "$MODE" in
  default)         [[ $exit_code -eq 1 ]] || { fail "Drill assertion: default mode should trigger rollback"; exit 3; } ;;
  happy-path)      [[ $exit_code -eq 0 ]] || { fail "Drill assertion: happy-path should succeed"; exit 3; } ;;
  readiness-fail)  [[ $exit_code -eq 1 ]] || { fail "Drill assertion: readiness-fail should rollback"; exit 3; } ;;
esac

ok "Drill assertion passed."
exit 0
