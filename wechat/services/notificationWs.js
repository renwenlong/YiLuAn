const config = require('../config/index')
const { getAccessToken } = require('../utils/token')

let _socketTask = null
let _heartbeatTimer = null
let _reconnectCount = 0
let _notificationCallback = null
const MAX_RECONNECT = 5
const HEARTBEAT_INTERVAL = 30000

function connect(options) {
  if (options && options.onNotification) {
    _notificationCallback = options.onNotification
  }

  var token = getAccessToken()
  if (!token) return

  var url = config.WS_BASE_URL + '/api/v1/ws/notifications?token=' + token

  _socketTask = wx.connectSocket({
    url: url,
    success: function () {},
    fail: function (err) {
      console.error('[NotifyWS] connect fail:', err)
    },
  })

  _socketTask.onOpen(function () {
    _reconnectCount = 0
    _startHeartbeat()
  })

  _socketTask.onMessage(function (res) {
    var data = typeof res.data === 'string' ? JSON.parse(res.data) : res.data
    if (data.type === 'pong') return
    if (_notificationCallback) _notificationCallback(data)
  })

  _socketTask.onClose(function () {
    _stopHeartbeat()
    if (_reconnectCount < MAX_RECONNECT) {
      var delay = Math.min(1000 * Math.pow(2, _reconnectCount), 30000)
      _reconnectCount++
      setTimeout(function () {
        connect({ onNotification: _notificationCallback })
      }, delay)
    }
  })

  _socketTask.onError(function () {
    _stopHeartbeat()
  })
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
  _heartbeatTimer = setInterval(function () {
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

module.exports = { connect, disconnect }
