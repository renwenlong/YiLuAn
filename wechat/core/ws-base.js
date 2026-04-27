/**
 * WSBase — 统一 WebSocket 基类（C-12 / TD-MSG-04 / TD-MSG-01）
 *
 * 抽离自 services/websocket.js + services/notificationWs.js（95% 重复代码）。
 * 单文件实现：构造一次 = 一条独立的 WS 通道。
 *
 * 能力：
 *  - connect(url, params?)        建连
 *  - reconnect()                  指数退避（1/2/5/10/30s 上限）
 *  - heartbeat                    30s PING / 自动启停
 *  - send(payload, opts)          自动注入客户端 nonce + 5min LRU 去重
 *  - disconnect()                 主动关闭并停掉重连
 *  - on(event, handler)           open / message / close / error / reconnect
 *
 * 不依赖 wx 全局：测试时通过 `socketFactory` 注入 mock。
 *
 * frame 契约（与后端 ChatService 协商，不变更）：
 *   上行 text/image/system: { type, content, nonce? }
 *   上行 ping:              { type: 'ping' }
 *   下行 pong:              { type: 'pong' }   ← 默认吞掉，不向上抛
 *   下行 broadcast:         { id, order_id, sender_id, type, content, ... }
 */

const DEFAULT_BACKOFF_LADDER_MS = [1000, 2000, 5000, 10000, 30000]
const DEFAULT_HEARTBEAT_MS = 30000
const DEFAULT_NONCE_TTL_MS = 5 * 60 * 1000 // 5min, matches backend Redis TTL

function _nanoid(size) {
  // No crypto module in 小程序 runtime; Date+Math.random() is sufficient
  // for a 16-char client nonce that only needs to be unique-per-user-per-5min.
  size = size || 16
  let out = Date.now().toString(36)
  while (out.length < size) {
    out += Math.random().toString(36).slice(2)
  }
  return out.slice(0, size)
}

function WSBase(options) {
  options = options || {}
  this._socketFactory =
    options.socketFactory ||
    function (cfg) {
      return wx.connectSocket(cfg)
    }
  this._heartbeatMs = options.heartbeatMs || DEFAULT_HEARTBEAT_MS
  this._backoffLadder = options.backoffLadder || DEFAULT_BACKOFF_LADDER_MS
  this._maxReconnect = options.maxReconnect != null ? options.maxReconnect : 5
  this._nonceTtlMs = options.nonceTtlMs || DEFAULT_NONCE_TTL_MS
  this._setTimeout =
    options.setTimeout ||
    (typeof setTimeout !== 'undefined' ? setTimeout : null)
  this._clearTimeout =
    options.clearTimeout ||
    (typeof clearTimeout !== 'undefined' ? clearTimeout : null)
  this._setInterval =
    options.setInterval ||
    (typeof setInterval !== 'undefined' ? setInterval : null)
  this._clearInterval =
    options.clearInterval ||
    (typeof clearInterval !== 'undefined' ? clearInterval : null)

  this._url = null
  this._socket = null
  this._heartbeatTimer = null
  this._reconnectTimer = null
  this._reconnectCount = 0
  this._stopped = false
  this._handlers = { open: [], message: [], close: [], error: [], reconnect: [] }

  // nonce LRU: Map<nonce, expiresAtMs>
  this._sentNonces = new Map()
}

WSBase.prototype.on = function (event, handler) {
  if (!this._handlers[event]) this._handlers[event] = []
  this._handlers[event].push(handler)
  return this
}

WSBase.prototype._emit = function (event, payload) {
  const list = this._handlers[event] || []
  for (let i = 0; i < list.length; i++) {
    try {
      list[i](payload)
    } catch (e) {
      // never let a faulty handler crash the socket loop
      console.error('[WSBase] handler error:', e)
    }
  }
}

WSBase.prototype.connect = function (url) {
  if (url) this._url = url
  if (!this._url) throw new Error('WSBase.connect: missing url')
  this._stopped = false

  const self = this
  this._socket = this._socketFactory({
    url: this._url,
    success: function () {},
    fail: function (err) {
      console.error('[WSBase] connect fail:', err)
    },
  })

  this._socket.onOpen(function () {
    self._reconnectCount = 0
    self._startHeartbeat()
    self._emit('open')
  })

  this._socket.onMessage(function (res) {
    let data
    try {
      data = typeof res.data === 'string' ? JSON.parse(res.data) : res.data
    } catch (e) {
      return
    }
    if (data && data.type === 'pong') return // swallow
    self._emit('message', data)
  })

  this._socket.onClose(function (evt) {
    self._stopHeartbeat()
    self._emit('close', evt)
    if (!self._stopped) self._scheduleReconnect()
  })

  this._socket.onError(function (err) {
    self._emit('error', err)
  })

  return this
}

WSBase.prototype._scheduleReconnect = function () {
  if (this._reconnectCount >= this._maxReconnect) return
  const idx = Math.min(this._reconnectCount, this._backoffLadder.length - 1)
  const delay = this._backoffLadder[idx]
  this._reconnectCount += 1
  const self = this
  if (!this._setTimeout) return
  this._reconnectTimer = this._setTimeout(function () {
    self._emit('reconnect', { attempt: self._reconnectCount, delay: delay })
    self.connect()
  }, delay)
}

WSBase.prototype.reconnect = function () {
  // public hook (manual)
  this._scheduleReconnect()
  return this
}

WSBase.prototype.disconnect = function () {
  this._stopped = true
  this._stopHeartbeat()
  if (this._reconnectTimer && this._clearTimeout) {
    this._clearTimeout(this._reconnectTimer)
    this._reconnectTimer = null
  }
  if (this._socket && this._socket.close) {
    try {
      this._socket.close()
    } catch (e) {
      // ignore
    }
  }
  this._socket = null
}

WSBase.prototype.send = function (payload, opts) {
  opts = opts || {}
  payload = payload || {}

  // TD-MSG-01: 客户端 nonce 幂等
  const withNonce = opts.withNonce !== false // default true
  if (withNonce && !payload.nonce) {
    payload.nonce = _nanoid(16)
  }

  this._gcNonces()
  if (payload.nonce) {
    if (this._sentNonces.has(payload.nonce)) {
      // duplicate send (e.g. user double-tap or reconnect-replay) → short-circuit
      return { sent: false, deduped: true, nonce: payload.nonce }
    }
    this._sentNonces.set(payload.nonce, Date.now() + this._nonceTtlMs)
  }

  if (!this._socket || !this._socket.send) {
    return { sent: false, deduped: false, nonce: payload.nonce }
  }
  this._socket.send({ data: JSON.stringify(payload) })
  return { sent: true, deduped: false, nonce: payload.nonce }
}

WSBase.prototype._gcNonces = function () {
  const now = Date.now()
  // Map iteration is insertion-ordered; bail at first non-expired entry.
  const it = this._sentNonces.entries()
  let cur = it.next()
  while (!cur.done) {
    const entry = cur.value
    if (entry[1] > now) break
    this._sentNonces.delete(entry[0])
    cur = it.next()
  }
}

WSBase.prototype._startHeartbeat = function () {
  this._stopHeartbeat()
  if (!this._setInterval) return
  const self = this
  this._heartbeatTimer = this._setInterval(function () {
    if (self._socket && self._socket.send) {
      try {
        self._socket.send({ data: JSON.stringify({ type: 'ping' }) })
      } catch (e) {
        // swallow — close handler will deal with it
      }
    }
  }, this._heartbeatMs)
}

WSBase.prototype._stopHeartbeat = function () {
  if (this._heartbeatTimer && this._clearInterval) {
    this._clearInterval(this._heartbeatTimer)
    this._heartbeatTimer = null
  }
}

module.exports = { WSBase: WSBase, _nanoid: _nanoid }
