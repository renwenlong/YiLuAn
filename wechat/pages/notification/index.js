const { getNotifications, getUnreadCount, markRead, markAllRead } = require('../../services/notification')

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
        })
        .catch(() => {})
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
