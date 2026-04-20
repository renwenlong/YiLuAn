const { getNotifications, getUnreadCount, markRead, markAllRead } = require('../../services/notification')
const store = require('../../store/index')

function getNavigationUrl(notification) {
  var type = notification.type
  var refId = notification.reference_id
  var state = store.getState()
  var role = (state.user && state.user.role) || 'patient'
  var orderDetailBase = role === 'companion'
    ? '/pages/companion/order-detail/index'
    : '/pages/patient/order-detail/index'

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
    const url = item ? getNavigationUrl(item) : null

    const doNavigate = function () {
      if (url) {
        wx.navigateTo({ url: url })
      }
    }

    if (!isRead) {
      markRead(id)
        .then(() => {
          const notifications = this.data.notifications.map(n => {
            if (n.id === id) return Object.assign({}, n, { is_read: true })
            return n
          })
          this.setData({
            notifications: notifications,
            unreadCount: Math.max(0, this.data.unreadCount - 1),
          })
          doNavigate()
        })
        .catch(() => {})
    } else {
      doNavigate()
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
