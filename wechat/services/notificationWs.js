/**
 * services/notificationWs.js — 全局通知 WS 业务薄壳（C-12 重构后）。
 *
 * 与 services/websocket.js 同源（共享 wechat/core/ws-base），消除原 95% 重复代码。
 * 暴露 API 与重构前一致：connect({ onNotification }) / disconnect()。
 */
const config = require('../config/index')
const { getAccessToken } = require('../utils/token')
const { WSBase } = require('../core/ws-base')

let _instance = null
let _notificationCallback = null

function _getInstance() {
  if (_instance) return _instance
  _instance = new WSBase()
  _instance.on('message', function (data) {
    // pong 已被 WSBase 吞掉
    if (_notificationCallback) _notificationCallback(data)
  })
  return _instance
}

function connect(options) {
  if (options && options.onNotification) {
    _notificationCallback = options.onNotification
  }
  const token = getAccessToken()
  if (!token) return

  const url =
    config.WS_BASE_URL + '/api/v1/ws/notifications?token=' + token

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
