#!/usr/bin/env bash
# dev-backend-up.sh — 在 127.0.0.1:8000 启动 backend 裸进程（dev / 小程序联调用）
#
# 设计：
#   - 端口 8000 = backend 裸跑（dev / 小程序 / iOS 联调）
#   - 端口 18080 = staging nginx 容器（ADR-0030），本脚本不碰
#
# 用法：
#   scripts/dev-backend-up.sh            # 启动（已在跑则提示）
#   scripts/dev-backend-up.sh restart    # 重启
#   scripts/dev-backend-up.sh stop       # 停止
#   scripts/dev-backend-up.sh status     # 看状态
#   scripts/dev-backend-up.sh logs       # tail 日志
#
# 启动后的健康检查：
#   curl http://127.0.0.1:8000/health
#   curl http://127.0.0.1:8000/api/v1/ping

set -euo pipefail

PORT="${PORT:-8000}"
HOST="${HOST:-127.0.0.1}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="${REPO_ROOT}/backend"
VENV_UVICORN="${BACKEND_DIR}/.venv/bin/uvicorn"
LOG_FILE="${LOG_FILE:-/tmp/yiluan-backend-${PORT}.log}"
PID_FILE="${PID_FILE:-/tmp/yiluan-backend-${PORT}.pid}"

cmd="${1:-up}"

is_running() {
  if [[ -f "${PID_FILE}" ]]; then
    local pid
    pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
    if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
      echo "${pid}"
      return 0
    fi
  fi
  # 兜底：按端口找
  local pid
  pid="$(ss -tlnp 2>/dev/null | awk -v p=":${PORT}" '$4 ~ p {print $0}' | grep -oP 'pid=\K[0-9]+' | head -n1 || true)"
  if [[ -n "${pid}" ]]; then
    echo "${pid}"
    return 0
  fi
  return 1
}

do_start() {
  if pid="$(is_running)"; then
    echo "✅ 已在运行 PID=${pid}  端口=${PORT}  日志=${LOG_FILE}"
    return 0
  fi
  if [[ ! -x "${VENV_UVICORN}" ]]; then
    echo "❌ 找不到 ${VENV_UVICORN}，请先在 backend/ 里建好 .venv 并装依赖" >&2
    exit 1
  fi
  cd "${BACKEND_DIR}"
  echo "🚀 启动 backend on ${HOST}:${PORT} ..."
  nohup "${VENV_UVICORN}" app.main:app --host "${HOST}" --port "${PORT}" \
    >"${LOG_FILE}" 2>&1 &
  echo $! >"${PID_FILE}"
  sleep 2
  for _ in 1 2 3 4 5; do
    if curl -fsS -m 2 "http://${HOST}:${PORT}/health" >/dev/null 2>&1; then
      echo "✅ backend ready  PID=$(cat "${PID_FILE}")  http://${HOST}:${PORT}"
      echo "   日志：tail -f ${LOG_FILE}"
      return 0
    fi
    sleep 1
  done
  echo "⚠️ 启动 5s 内 /health 未就绪，看日志：${LOG_FILE}" >&2
  tail -20 "${LOG_FILE}" >&2 || true
  exit 1
}

do_stop() {
  if pid="$(is_running)"; then
    echo "🛑 停止 PID=${pid}"
    kill "${pid}" 2>/dev/null || true
    sleep 1
    kill -0 "${pid}" 2>/dev/null && kill -9 "${pid}" 2>/dev/null || true
    rm -f "${PID_FILE}"
    echo "✅ 已停"
  else
    echo "ℹ️ 没在跑"
    rm -f "${PID_FILE}" 2>/dev/null || true
  fi
}

do_status() {
  if pid="$(is_running)"; then
    echo "✅ running  PID=${pid}  port=${PORT}"
    curl -sS -m 2 -o /dev/null -w "   /health -> %{http_code}\n" "http://${HOST}:${PORT}/health" || true
    curl -sS -m 2 -o /dev/null -w "   /api/v1/ping -> %{http_code}\n" "http://${HOST}:${PORT}/api/v1/ping" || true
  else
    echo "❌ not running"
    exit 1
  fi
}

case "${cmd}" in
  up|start)   do_start ;;
  stop|down)  do_stop ;;
  restart)    do_stop; do_start ;;
  status)     do_status ;;
  logs)       tail -f "${LOG_FILE}" ;;
  *) echo "用法: $0 {up|stop|restart|status|logs}"; exit 2 ;;
esac
