#!/usr/bin/env bash
# =============================================================================
# metrics_baseline.sh —— Prometheus /metrics 24 小时基线采集脚本
# -----------------------------------------------------------------------------
# 用途：每 30 秒拉取一次本机后端 /metrics 端点的快照，追加到当日日志文件，
#       连续运行 24 小时（共 2880 个样本），用于设定告警阈值的基线分析。
#
# 关联：
#   - A-2604-06（2026-04-24 晨会 Action Item）
#   - SP-03 可观测性 / Ops 24h 基线采样
#   - prometheus/alerts.yml（5 条告警的阈值校准依据）
#
# 输出：ops/baselines/metrics-YYYY-MM-DD.log（追加模式，每个样本前带时间戳头）
#
# 使用：
#   bash ops/scripts/metrics_baseline.sh                 # 前台运行 24h
#   nohup bash ops/scripts/metrics_baseline.sh &         # 后台运行 24h
#
# 退出条件：
#   - 累计运行 86400 秒（24h）后正常退出 0
#   - 收到 SIGINT/SIGTERM 时打印总采样数后退出 0
# =============================================================================
set -euo pipefail

# ----- 可调参数（可通过环境变量覆盖） ----------------------------------------
METRICS_URL="${METRICS_URL:-http://localhost:8000/metrics}"
INTERVAL_SEC="${INTERVAL_SEC:-30}"
DURATION_SEC="${DURATION_SEC:-86400}"   # 24h
# 输出目录：脚本所在目录的上级 baselines/
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="${OUT_DIR:-${SCRIPT_DIR}/../baselines}"
mkdir -p "${OUT_DIR}"
LOG_FILE="${OUT_DIR}/metrics-$(date +%F).log"

# ----- 计数器与信号处理 -------------------------------------------------------
SAMPLES=0
START_TS=$(date +%s)

cleanup() {
  echo "[metrics_baseline] received signal, collected ${SAMPLES} samples in $(( $(date +%s) - START_TS ))s, exiting." >&2
  exit 0
}
trap cleanup INT TERM

echo "[metrics_baseline] start url=${METRICS_URL} interval=${INTERVAL_SEC}s duration=${DURATION_SEC}s out=${LOG_FILE}" >&2

# ----- 主循环：固定时长，按 INTERVAL_SEC 节奏采样 -----------------------------
END_TS=$(( START_TS + DURATION_SEC ))
while [ "$(date +%s)" -lt "${END_TS}" ]; do
  TS_ISO="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  {
    echo "# === sample @ ${TS_ISO} ==="
    # --max-time 兜底，避免后端阻塞拖死整个采样
    if ! curl -fsS --max-time 10 "${METRICS_URL}"; then
      echo "# WARN: curl failed at ${TS_ISO}"
    fi
    echo ""
  } >> "${LOG_FILE}"
  SAMPLES=$(( SAMPLES + 1 ))
  sleep "${INTERVAL_SEC}"
done

echo "[metrics_baseline] done, collected ${SAMPLES} samples to ${LOG_FILE}" >&2
