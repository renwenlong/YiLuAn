/**
 * services/precheckWs.js — S3-DEV-003-TRUST-UI-WX precheck WS push +
 *                          polling fallback (S3-DEV-003-TRUST-UI-WX-POLLING-FALLBACK).
 *
 * 订单级 WS 通道 `/api/v1/ws/v1/orders/{order_id}/precheck`:
 *   - precheck.status.updated — 单 card 状态更新 (本 task 关心 cert)
 *   - precheck.all_ready      — 4 card 全 ready
 *   - precheck.blocked        — 至少 1 card red with reason
 *
 * 收到任一 event 后调 onEvent 回调, 上层 page 应当 **重新 GET HTTP**
 * 拿最新 summary (后端 design: WS 是触发 + payload 摘要, HTTP 是 source of truth).
 *
 * # Polling fallback (S3-DEV-003-TRUST-UI-WX-POLLING-FALLBACK)
 *
 * 跨端对齐 iOS `PrecheckViewModel.startPolling` (30s, isPollingFallback @Published).
 *
 * 触发逻辑:
 *   - WS close (非永久失败 code 4001/4003/4004/4011) → 启 polling
 *   - WS authenticated (收到 ws-base 'authenticated' event) → 停 polling 互斥
 *   - 永久失败 code → 不 fallback, 让 onConnectionState callback 上报 errorMessage
 *
 * Polling 调用方式: 由 page 注入 `onShouldRefresh()` 回调 (page 内调
 * `getOrderPrecheckStatus(orderId)` HTTP 刷). 这样 precheckWs 不需直接依赖
 * services/precheck.js (避免循环 require, 同时 page 可自决 refresh 失败处理).
 *
 * # 与 services/notificationWs.js 共享 core/ws-base 的 first-frame auth +
 *   pong/reconnect/jitter. order_id 内嵌 URL — 单订单页面 lifecycle scoped.
 *
 * # ws-base 'authenticated' event (本 task 顺带引入)
 *
 * 原 ws-base 在 line 159 swallow 了 `auth_ok` ack 不向上报. 本 task 在 ws-base
 * 内 emit 一个 `authenticated` event (零破坏, 不监听不影响), 使 precheckWs 能
 * 精确捕获 auth 成功信号触发 stopPolling, 与 iOS `onAuthOK` 语义对齐.
 */
const config = require('../config/index')
const { getAccessToken } = require('../utils/token')
const { WSBase } = require('../core/ws-base')
const logger = require('../utils/logger')

// Polling fallback 周期 (跨端对齐 iOS PrecheckViewModel.pollingInterval = 30s).
const POLLING_INTERVAL_MS = 30000

// 永久失败 close code: 不启 polling fallback, 报错给上层 (跨端对齐 iOS).
//   4001: 鉴权失败 (token 无效)
//   4003: 鉴权失败 (token 过期)
//   4004: 资源不存在 (order_id 404)
//   4011: ABAC 拒绝 (跨患者访问)
const PERMANENT_FAILURE_CODES = [4001, 4003, 4004, 4011]

let _instance = null
let _currentOrderId = null
let _eventCallback = null
// Polling 状态 (跨 module 共享, 因为 _instance 也是 module-level singleton).
let _pollingTimer = null
let _pollingActive = false
// Page 注入的 refresh 回调; null 时 polling tick 仅 logger.info 不发请求.
let _onShouldRefresh = null
// Page 注入的 connection state callback (传递 polling 激活 + 永久失败信号).
let _onConnectionState = null

function _setPollingActive(active, reason) {
  if (_pollingActive === active) return
  _pollingActive = active
  if (_onConnectionState) {
    try {
      _onConnectionState({
        isPollingFallback: active,
        reason: reason || null,
      })
    } catch (e) {
      logger.warn('[precheckWs] onConnectionState callback threw', {
        msg: e && (e.message || String(e)),
      })
    }
  }
}

function _startPolling(reason) {
  if (_pollingTimer) return  // 互斥, 已在 polling
  logger.info('[precheckWs] start polling fallback', {
    orderId: _currentOrderId,
    intervalMs: POLLING_INTERVAL_MS,
    reason: reason || 'ws_closed',
  })
  _setPollingActive(true, reason)
  _pollingTimer = setInterval(function () {
    if (_onShouldRefresh) {
      try {
        var ret = _onShouldRefresh()
        // 支持 Promise / sync — 失败 logger.warn 不停 polling
        if (ret && typeof ret.then === 'function') {
          ret.catch(function (err) {
            logger.warn('[precheckWs] polling refresh failed', {
              orderId: _currentOrderId,
              msg: err && (err.message || String(err)),
            })
          })
        }
      } catch (e) {
        logger.warn('[precheckWs] polling refresh threw', {
          orderId: _currentOrderId,
          msg: e && (e.message || String(e)),
        })
      }
    }
  }, POLLING_INTERVAL_MS)
  // 避免 jest "open handle" warnings (同 page 内 _countdownTimer pattern).
  if (_pollingTimer && typeof _pollingTimer.unref === 'function') {
    _pollingTimer.unref()
  }
}

function _stopPolling(reason) {
  if (!_pollingTimer) return
  logger.info('[precheckWs] stop polling fallback', {
    orderId: _currentOrderId,
    reason: reason || 'ws_authenticated',
  })
  clearInterval(_pollingTimer)
  _pollingTimer = null
  _setPollingActive(false, reason)
}

function _getInstance() {
  if (_instance) return _instance
  _instance = new WSBase({
    // First-frame auth handshake (consistent with notificationWs / shareWs):
    // token resolved lazily on each (re)connect, reflects latest access
    // token after refresh.
    authPayload: function () {
      var token = getAccessToken()
      if (!token) return null
      return { type: 'auth', token: token }
    },
  })
  _instance.on('message', function (data) {
    // pong / auth_ok 已被 WSBase 吞掉; 这里只见 precheck.* event envelope.
    if (_eventCallback) _eventCallback(data)
  })
  _instance.on('authenticated', function () {
    // ws-base 收到 auth_ok ack → 跨端对齐 iOS onAuthOK 信号
    // → 停 polling fallback (WS 已上线, polling 互斥).
    _stopPolling('ws_authenticated')
  })
  _instance.on('error', function (err) {
    var msg = err && (err.errMsg || err.message) || ''
    logger.warn('[precheckWs] error', {
      orderId: _currentOrderId,
      msg: msg,
    })
  })
  _instance.on('close', function (evt) {
    logger.info('[precheckWs] close', { orderId: _currentOrderId, evt: evt || null })
    // 跨端对齐 iOS: 永久失败 code 不启 polling, 报错给上层.
    var code = evt && evt.code
    if (PERMANENT_FAILURE_CODES.indexOf(code) >= 0) {
      logger.warn('[precheckWs] permanent failure, not falling back to polling', {
        orderId: _currentOrderId,
        code: code,
        reason: evt && evt.reason,
      })
      if (_onConnectionState) {
        try {
          _onConnectionState({
            isPollingFallback: false,
            permanentFailure: true,
            code: code,
            reason: (evt && evt.reason) || null,
          })
        } catch (e) {
          logger.warn('[precheckWs] onConnectionState callback threw', {
            msg: e && (e.message || String(e)),
          })
        }
      }
      return
    }
    // 临时失败 (idle / network / unknown) → 启 polling fallback.
    _startPolling('ws_closed_code_' + (code != null ? code : 'unknown'))
  })
  _instance.on('reconnect', function (info) {
    logger.info('[precheckWs] reconnect', {
      orderId: _currentOrderId,
      attempt: info.attempt,
      delay: info.delay,
    })
  })
  return _instance
}

/**
 * @param {Object} options
 * @param {string} options.orderId — 订单 UUID
 * @param {function(Object): void} options.onEvent — 收到 precheck.* event 回调
 * @param {function(): (void|Promise)} [options.onShouldRefresh] — polling tick
 *        触发的 HTTP refresh 回调 (e.g. page 内 `_loadPrecheck`). 不传则 polling
 *        tick 仅 logger.info 不发请求 (defensive — 但 page 应总传).
 * @param {function(Object): void} [options.onConnectionState] — connection
 *        state 变化回调. payload:
 *        - { isPollingFallback: boolean, reason: string|null }
 *        - 或 permanent failure: { isPollingFallback: false, permanentFailure:
 *          true, code: number, reason: string|null }
 */
function connect(options) {
  if (!options || !options.orderId) {
    logger.warn('[precheckWs] connect skipped: orderId required')
    return
  }
  _currentOrderId = options.orderId
  if (options.onEvent) _eventCallback = options.onEvent
  if (options.onShouldRefresh) _onShouldRefresh = options.onShouldRefresh
  if (options.onConnectionState) _onConnectionState = options.onConnectionState
  const token = getAccessToken()
  if (!token) {
    logger.warn('[precheckWs] connect skipped: no access token')
    return
  }
  // URL 不带 token query — 鉴权走 onOpen 后 authPayload first frame,
  // 与生产 nginx access log / 代理 trace 安全策略一致.
  var url = config.WS_BASE_URL + '/api/v1/ws/v1/orders/' + options.orderId + '/precheck'
  var inst = _getInstance()
  inst.connect(url)
}

function disconnect() {
  // 停 polling 兜底 (清理 timer 避免 page leave 后还跑 HTTP).
  _stopPolling('disconnect')
  if (!_instance) return
  _instance.disconnect()
  _instance = null
  _currentOrderId = null
  _eventCallback = null
  _onShouldRefresh = null
  _onConnectionState = null
}

// Exposed for tests (允许 isolation 检查 polling 状态).
function _isPollingActiveForTests() {
  return _pollingActive
}

module.exports = {
  connect: connect,
  disconnect: disconnect,
  // Constants exported for tests / page consumers (避免 magic number).
  POLLING_INTERVAL_MS: POLLING_INTERVAL_MS,
  PERMANENT_FAILURE_CODES: PERMANENT_FAILURE_CODES,
  // Test seam (do not call from production code).
  _isPollingActiveForTests: _isPollingActiveForTests,
}
