const store = require('./store/index')
const { getAccessToken, isTokenExpired } = require('./utils/token')
const { getMe } = require('./services/user')
const { logout } = require('./services/auth')
const notificationWs = require('./services/notificationWs')
const { syncTabBarBadge } = require('./utils/badge')

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
    const accessToken = getAccessToken()
    if (accessToken && !isTokenExpired(accessToken)) {
      store.setState({ isAuthenticated: true })
      // 已登录 → 立即建立全局通知连接
      this.connectNotificationWs()
      getMe().then(user => {
        store.setState({ user })
      }).catch(() => {
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
