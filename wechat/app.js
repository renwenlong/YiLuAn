const store = require('./store/index')
const { getAccessToken, isTokenExpired } = require('./utils/token')
const { getMe } = require('./services/user')
const { logout } = require('./services/auth')
const notificationWs = require('./services/notificationWs')
const { syncTabBarBadge } = require('./utils/badge')

// 把任意 reject reason 序列化成可读字符串：抓 Error 的 name+message+stack，
// 抓 wx fail 风格的 {errMsg,errno,...}，抓所有可枚举字段。目的是让一条
// `Error: timeout` 能告诉你「谁 throw 的、在哪条 stack」。
function _dumpReason(reason) {
  if (reason == null) return String(reason)
  if (typeof reason === 'string') return reason
  try {
    if (reason instanceof Error) {
      var extra = {}
      Object.keys(reason).forEach(function (k) { extra[k] = reason[k] })
      var extraStr = Object.keys(extra).length ? ' extra=' + JSON.stringify(extra) : ''
      return (reason.name || 'Error') + ': ' + reason.message + extraStr + '\nstack: ' + (reason.stack || '(no stack)')
    }
    return JSON.stringify(reason)
  } catch (e) {
    return String(reason)
  }
}

// 全局通知订阅者列表
const _notificationSubscribers = []

function _dispatchNotification(data) {
  // 简易的全局未读角标 badge 计数（系统通知 / 新订单 / 新消息）
  var nextUnread = 0
  try {
    const state = store.getState ? store.getState() : {}
    nextUnread = (state.unreadCount || 0) + 1
    store.setState({ unreadCount: nextUnread, lastNotification: data })
  } catch (e) {
    // ignore
  }
  syncTabBarBadge(nextUnread)
  _notificationSubscribers.forEach(function (cb) {
    try {
      cb(data)
    } catch (e) {
      // 单个订阅者异常不影响其他订阅者
      console.error('[App] notification subscriber error:', e)
    }
  })
}

App({
  globalData: {
    store: store,
    notificationWsConnected: false,
  },

  /**
   * 全局订阅通知。返回 unsubscribe 函数。
   * 页面在 onLoad 里调用，onUnload 里调用返回值解绑。
   */
  subscribeNotification(callback) {
    if (typeof callback !== 'function') return function () {}
    _notificationSubscribers.push(callback)
    return () => {
      const idx = _notificationSubscribers.indexOf(callback)
      if (idx >= 0) _notificationSubscribers.splice(idx, 1)
    }
  },

  /**
   * 全局建立通知 WebSocket 连接。登录成功或应用启动发现已登录时调用。
   * 重复调用是幂等的（notificationWs 内部会先清理旧连接再连新的）。
   */
  connectNotificationWs() {
    try {
      notificationWs.connect({ onNotification: _dispatchNotification })
      this.globalData.notificationWsConnected = true
    } catch (e) {
      console.error('[App] connectNotificationWs error:', e)
    }
  },

  /**
   * 全局断开通知 WebSocket。登出时调用。
   */
  disconnectNotificationWs() {
    try {
      notificationWs.disconnect()
    } catch (e) {
      // ignore
    }
    this.globalData.notificationWsConnected = false
  },

  /**
   * 页面进入消息列表时调用：清空未读 + 移除 TabBar 角标。
   */
  clearUnreadBadge() {
    try {
      store.setState({ unreadCount: 0 })
    } catch (e) {
      // ignore
    }
    syncTabBarBadge(0)
  },

  /**
   * 手动设置未读并联动角标。主要用于测试 / REST 初始化。
   */
  setUnreadBadge(count) {
    var n = Math.max(0, parseInt(count, 10) || 0)
    try {
      store.setState({ unreadCount: n })
    } catch (e) {
      // ignore
    }
    syncTabBarBadge(n)
  },

  onLaunch() {
    // 全局兜底：捕获未处理的 Promise reject（包括 wx 框架内部 timeout）与
    // 同步异常。主要场景：devtools 下 ws://localhost 走不通、后台临时 5xx、
    // 某条业务代码忘写 .catch、wx.login / wx.request / wx.connectSocket
    // 触发框架级 timeout 但调用方丢了 catch —— 之前这些会冲到控制台变成
    // 匿名 `Error: timeout`，现在统一抓回来 + 落 dump 到可读日志。
    if (typeof wx !== 'undefined') {
      if (typeof wx.onUnhandledRejection === 'function') {
        wx.onUnhandledRejection(function (res) {
          console.warn('[App] Unhandled promise rejection:', _dumpReason(res && res.reason))
        })
      }
      if (typeof wx.onError === 'function') {
        wx.onError(function (err) {
          var s = typeof err === 'string' ? err : (err && err.stack) || String(err)
          console.warn('[App] wx.onError:', s)
          if (/timeout/i.test(s)) {
            try {
              var cfg = require('./config/index')
              console.warn('[App] ^^ matches /timeout/. likely wx.{login|request|connectSocket} framework timeout — check reachability of', cfg.API_BASE_URL, '/', cfg.WS_BASE_URL)
            } catch (e) {}
          }
        })
      }
    }

    const accessToken = getAccessToken()
    if (accessToken && !isTokenExpired(accessToken)) {
      store.setState({ isAuthenticated: true })
      // 已登录 → 立即建立全局通知连接
      this.connectNotificationWs()
      getMe().then(user => {
        store.setState({ user })
      }).catch(err => {
        // 之前是裸 .catch(() => logout())，吞掉 reason → 没人知道是 401 还是 timeout。
        // 现在打印根因再下线。
        console.warn('[App] onLaunch getMe failed → logout:', _dumpReason(err))
        this.disconnectNotificationWs()
        logout()
      })
    }
  },

  /**
   * 前台恢复时，如果仍已登录但连接已断，则重连。notificationWs 内部自带
   * 断线重连，所以正常情况下这只是兜底。
   */
  onShow() {
    const accessToken = getAccessToken()
    if (accessToken && !isTokenExpired(accessToken) && !this.globalData.notificationWsConnected) {
      this.connectNotificationWs()
    }
  },

  onHide() {
    // 小程序切后台时不主动断开：微信会冻结 JS 线程，连接会自然进入 idle。
    // 如果后续证明耗电/服务端压力大可以改为在 onHide 断开、onShow 重连。
  },
})
