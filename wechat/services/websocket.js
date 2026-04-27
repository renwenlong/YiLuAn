/**
 * services/websocket.js — 订单聊天 WS 业务薄壳（C-12 重构后）。
 *
 * 真正的连接 / 重连 / 心跳 / nonce 由 wechat/core/ws-base 提供。
 * 本文件只负责：
 *   - 拼出 /api/v1/ws/chat/{orderId}?token=... 的 URL
 *   - 把 WSBase 暴露为 connect / send / onMessage / disconnect 的旧 API
 *
 * **向后兼容**：调用方（如 pages/chat）现有 require('services/websocket')
 * 调用形态不变。
 */
const config = require('../config/index')
const { getAccessToken } = require('../utils/token')
const { WSBase } = require('../core/ws-base')

let _instance = null
let _messageCallback = null
let _errorCallback = null

function _getInstance() {
  if (_instance) return _instance
  _instance = new WSBase()
  _instance.on('message', function (data) {
    if (_messageCallback) _messageCallback(data)
  })
  _instance.on('error', function (err) {
    if (_errorCallback) _errorCallback(err)
  })
  return _instance
}

function connect(options) {
  let orderId
  if (typeof options === 'object' && options !== null) {
    orderId = options.orderId
    if (options.onMessage) _messageCallback = options.onMessage
    if (options.onError) _errorCallback = options.onError
  } else {
    orderId = options
  }

  const token = getAccessToken()
  const url =
    config.WS_BASE_URL +
    '/api/v1/ws/chat/' +
    orderId +
    '?token=' +
    token

  const inst = _getInstance()
  inst.connect(url)
}

function send(message) {
  const inst = _getInstance()
  // 透传 — WSBase 会自动注入 nonce 并去重
  inst.send(message || {})
}

function onMessage(callback) {
  _messageCallback = callback
}

function disconnect() {
  if (!_instance) return
  _instance.disconnect()
  _instance = null
  _messageCallback = null
  _errorCallback = null
}

module.exports = { connect: connect, send: send, onMessage: onMessage, disconnect: disconnect }
