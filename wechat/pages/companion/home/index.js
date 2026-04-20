const { getOrders } = require('../../../services/order')
const { getCompanionStats } = require('../../../services/companion')
const { getUnreadCount } = require('../../../services/notification')
const store = require('../../../store/index')

Page({
  data: {
    stats: {
      openOrders: 0,
      totalEarnings: 0,
      rating: 0
    },
    pendingOrders: [],
    pendingTotal: 0,
    unreadCount: 0
  },

  onLoad() {
    this.fetchStats()
    this.fetchPendingOrders()
    this.fetchUnreadCount()
  },

  onShow() {
    this.fetchStats()
    this.fetchPendingOrders()
    this.fetchUnreadCount()
  },

  fetchUnreadCount() {
    var self = this
    getUnreadCount()
      .then(function (res) {
        var count = res.count || (res.data && res.data.count) || 0
        self.setData({ unreadCount: count })
      })
      .catch(function () {})
  },

  fetchStats() {
    var self = this
    getCompanionStats()
      .then(function (res) {
        var data = res.data || res
        self.setData({
          stats: {
            openOrders: data.open_orders || 0,
            totalEarnings: data.total_earnings || 0,
            rating: data.avg_rating != null ? data.avg_rating : 0
          }
        })
      })
      .catch(function (err) {
        console.error('获取统计失败', err)
      })
  },

  fetchPendingOrders() {
    var self = this
    var params = { status: 'created', page: 1, page_size: 3 }
    var state = store.getState()
    if (state && state.city) {
      params.city = state.city
    }
    getOrders(params)
      .then(function (res) {
        var list = res.items ? res.items : (res.data && res.data.items ? res.data.items : [])
        var total = res.total || (res.data && res.data.total) || list.length
        self.setData({ pendingOrders: list, pendingTotal: total })
      })
      .catch(function (err) {
        console.error('获取待接单列表失败', err)
      })
  },

  onViewAllPending() {
    wx.navigateTo({
      url: '/pages/companion/available-orders/index'
    })
  },

  onOpenOrdersTap() {
    wx.navigateTo({
      url: '/pages/companion/today-orders/index'
    })
  },

  onOrderTap(e) {
    var id = e.currentTarget.dataset.id
    wx.navigateTo({
      url: '/pages/companion/order-detail/index?id=' + id
    })
  },

  onNotificationTap() {
    wx.navigateTo({
      url: '/pages/notification/index'
    })
  }
})
