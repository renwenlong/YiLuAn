const { getNotifications, getUnreadCount, markRead, markAllRead } = require('../../services/notification')
const store = require('../../store/index')

/**
 * [F-02] 根据通知的 target_type/target_id 计算跳转 URL。
 * 优先使用新字段 target_type / target_id；为空时回退到旧字段 type / reference_id，
 * 保证后端尚未回填的历史数据也能跳转。
 */
function getNavigationUrl(notification) {
  var state = store.getState()
  var role = (state.user && state.user.role) || 'patient'
  var orderDetailBase = role === 'companion'
    ? '/pages/companion/order-detail/index'
    : '/pages/patient/order-detail/index'

  var targetType = notification.target_type
  var targetId = notification.target_id

  if (targetType && targetId) {
    switch (targetType) {
      case 'order':
        return orderDetailBase + '?id=' + targetId
      case 'companion':
        return '/pages/companion-detail/index?id=' + targetId
      case 'review':
        return '/pages/review/write/index?id=' + targetId
      case 'payment':
        return '/pages/patient/pay-result/index?id=' + targetId
      case 'system':
      default:
        return null
    }
  }

  // ---- 兼容旧字段 ----
  var type = notification.type
  var refId = notification.reference_id
  if (!type || !refId) return null

  switch (type) {
    case 'order_status_changed':
    case 'new_order':
    case 'start_service_request':
      return orderDetailBase + '?id=' + refId
    case 'new_message':
      return '/pages/chat/room/index?order_id=' + refId
    case 'review_received':
      return orderDetailBase + '?id=' + refId
    default:
      return null
  }
}

Page({
  data: {
    notifications: [],
    unreadCount: 0,
    loading: false,
    page: 1,
    hasMore: true,
  },

  onLoad() {
    this.fetchNotifications()
    this.fetchUnreadCount()
  },

  onShow() {
    this.fetchUnreadCount()
  },

  fetchNotifications() {
    if (this.data.loading) return
    this.setData({ loading: true })
    getNotifications({ page: this.data.page })
      .then(res => {
        const items = res.items || []
        this.setData({
          notifications: this.data.page === 1 ? items : this.data.notifications.concat(items),
          hasMore: items.length >= 20,
          loading: false,
        })
      })
      .catch(() => {
        this.setData({ loading: false })
      })
  },

  fetchUnreadCount() {
    getUnreadCount()
      .then(res => {
        this.setData({ unreadCount: res.count || 0 })
      })
      .catch(() => {})
  },

  onNotificationTap(e) {
    const id = e.currentTarget.dataset.id
    const isRead = e.currentTarget.dataset.read
    const item = this.data.notifications.find(n => n.id === id)

    const self = this
    const navigateFromItem = function (latest) {
      const target = latest || item
      const url = target ? getNavigationUrl(target) : null
      if (url) {
        wx.navigateTo({ url: url })
      }
    }

    if (!isRead) {
      markRead(id)
        .then(res => {
          // [F-02] 后端 markRead 现在返回 { success, notification }，用最新通知信息更新本地缓存
          const latest = (res && res.notification) || null
          const notifications = self.data.notifications.map(n => {
            if (n.id === id) {
              return Object.assign({}, n, latest || { is_read: true })
            }
            return n
          })
          self.setData({
            notifications: notifications,
            unreadCount: Math.max(0, self.data.unreadCount - 1),
          })
          navigateFromItem(latest)
        })
        .catch(() => {})
    } else {
      navigateFromItem(null)
    }
  },

  onMarkAllRead() {
    markAllRead()
      .then(() => {
        const notifications = this.data.notifications.map(n =>
          Object.assign({}, n, { is_read: true })
        )
        this.setData({ notifications: notifications, unreadCount: 0 })
      })
      .catch(() => {})
  },

  onPullDownRefresh() {
    this.setData({ page: 1, hasMore: true })
    this.fetchNotifications()
    this.fetchUnreadCount()
    wx.stopPullDownRefresh()
  },

  onReachBottom() {
    if (this.data.hasMore && !this.data.loading) {
      this.setData({ page: this.data.page + 1 })
      this.fetchNotifications()
    }
  },
})
