const config = require('../config/index')
const { getAccessToken } = require('../utils/token')

let _socketTask = null
let _heartbeatTimer = null
let _reconnectCount = 0
let _messageCallback = null
const MAX_RECONNECT = 5
const HEARTBEAT_INTERVAL = 30000

function connect(options) {
  let orderId, onErrorCallback
  if (typeof options === 'object') {
    orderId = options.orderId
    if (options.onMessage) _messageCallback = options.onMessage
    onErrorCallback = options.onError || null
  } else {
    orderId = options
  }

  const token = getAccessToken()
  const url = config.WS_BASE_URL + '/ws/chat/' + orderId + '?token=' + token

  _socketTask = wx.connectSocket({
    url,
    success() {},
    fail(err) {
      console.error('[WS] connect fail:', err)
    },
  })

  _socketTask.onOpen(() => {
    _reconnectCount = 0
    _startHeartbeat()
  })

  _socketTask.onMessage((res) => {
    const data = typeof res.data === 'string' ? JSON.parse(res.data) : res.data
    if (_messageCallback) _messageCallback(data)
  })

  _socketTask.onClose(() => {
    _stopHeartbeat()
    if (_reconnectCount < MAX_RECONNECT) {
      const delay = Math.min(1000 * Math.pow(2, _reconnectCount), 30000)
      _reconnectCount++
      setTimeout(() => connect({ orderId, onMessage: _messageCallback, onError: onErrorCallback }), delay)
    }
  })

  _socketTask.onError(() => {
    _stopHeartbeat()
    if (onErrorCallback) onErrorCallback()
  })
}

function send(message) {
  if (_socketTask) {
    _socketTask.send({
      data: JSON.stringify(message),
    })
  }
}

function onMessage(callback) {
  _messageCallback = callback
}

function disconnect() {
  _stopHeartbeat()
  _reconnectCount = MAX_RECONNECT
  if (_socketTask) {
    _socketTask.close()
    _socketTask = null
  }
}

function _startHeartbeat() {
  _stopHeartbeat()
  _heartbeatTimer = setInterval(() => {
    if (_socketTask) {
      _socketTask.send({ data: JSON.stringify({ type: 'ping' }) })
    }
  }, HEARTBEAT_INTERVAL)
}

function _stopHeartbeat() {
  if (_heartbeatTimer) {
    clearInterval(_heartbeatTimer)
    _heartbeatTimer = null
  }
}

module.exports = { connect, send, onMessage, disconnect }
