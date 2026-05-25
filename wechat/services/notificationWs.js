/**
 * services/notificationWs.js — 全局通知 WS 业务薄壳（C-12 重构后）。
 *
 * 与 services/websocket.js 同源（共享 wechat/core/ws-base），消除原 95% 重复代码。
 * 暴露 API 与重构前一致：connect({ onNotification }) / disconnect()。
 */
const config = require('../config/index')
const { getAccessToken } = require('../utils/token')
const { WSBase } = require('../core/ws-base')
const logger = require('../utils/logger')

let _instance = null
let _notificationCallback = null

function _getInstance() {
  if (_instance) return _instance
  _instance = new WSBase({
    // First-frame auth handshake (replaces ?token= query param). The token
    // is resolved lazily on each (re)connect so it always reflects the
    // latest access token after a refresh.
    authPayload: function () {
      var token = getAccessToken()
      if (!token) return null
      return { type: 'auth', token: token }
    },
  })
  _instance.on('message', function (data) {
    // pong / auth_ok 已被 WSBase 吞掉
    if (_notificationCallback) _notificationCallback(data)
  })
  // 之前没注册 error/close/reconnect → WS 异常静默被吞，devtools 里只能看到
  // 上层调用挂死。把这些日志拉出来，配合全局 unhandledRejection 兜底一起
  // 定位 `Error: timeout` 真实根因。
  _instance.on('error', function (err) {
    var msg = err && (err.errMsg || err.message) || ''
    logger.warn('[notificationWs] error', { msg: msg, err: err && (err.errMsg || err.message || String(err)) })
  })
  _instance.on('close', function (evt) {
    logger.info('[notificationWs] close', { evt: evt || null })
  })
  _instance.on('reconnect', function (info) {
    logger.info('[notificationWs] reconnect', { attempt: info.attempt, delay: info.delay })
  })
  return _instance
}

function connect(options) {
  if (options && options.onNotification) {
    _notificationCallback = options.onNotification
  }
  const token = getAccessToken()
  if (!token) return

  // Token 不再出现在 URL 里 — 生产环境避免被 nginx access log /
  // 代理 trace / 抓包工具记录。鉴权走 onOpen 后的 authPayload。
  const url = config.WS_BASE_URL + '/api/v1/ws/notifications'

  const inst = _getInstance()
  inst.connect(url)
}

function disconnect() {
  if (!_instance) return
  _instance.disconnect()
  _instance = null
  _notificationCallback = null
}

module.exports = { connect: connect, disconnect: disconnect }
