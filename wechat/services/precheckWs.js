/**
 * services/precheckWs.js — S3-DEV-003-TRUST-UI-WX precheck WS push.
 *
 * 订单级 WS 通道 `/api/v1/ws/v1/orders/{order_id}/precheck`:
 *   - precheck.status.updated — 单 card 状态更新 (本 task 关心 cert)
 *   - precheck.all_ready      — 4 card 全 ready
 *   - precheck.blocked        — 至少 1 card red with reason
 *
 * 收到任一 event 后调 onEvent 回调, 上层 page 应当 **重新 GET HTTP**
 * 拿最新 summary (后端 design: WS 是触发 + payload 摘要, HTTP 是 source of truth).
 *
 * 与 services/notificationWs.js 共享 core/ws-base 的 first-frame auth +
 * pong/reconnect/jitter. order_id 内嵌 URL — 单订单页面 lifecycle scoped.
 */
const config = require('../config/index')
const { getAccessToken } = require('../utils/token')
const { WSBase } = require('../core/ws-base')
const logger = require('../utils/logger')

let _instance = null
let _currentOrderId = null
let _eventCallback = null

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
  _instance.on('error', function (err) {
    var msg = err && (err.errMsg || err.message) || ''
    logger.warn('[precheckWs] error', {
      orderId: _currentOrderId,
      msg: msg,
    })
  })
  _instance.on('close', function (evt) {
    logger.info('[precheckWs] close', { orderId: _currentOrderId, evt: evt || null })
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
 */
function connect(options) {
  if (!options || !options.orderId) {
    logger.warn('[precheckWs] connect skipped: orderId required')
    return
  }
  _currentOrderId = options.orderId
  if (options.onEvent) _eventCallback = options.onEvent
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
  if (!_instance) return
  _instance.disconnect()
  _instance = null
  _currentOrderId = null
  _eventCallback = null
}

module.exports = {
  connect: connect,
  disconnect: disconnect,
}
