const { getOrders } = require('../../../services/order')
const { getCompanionStats } = require('../../../services/companion')
const store = require('../../../store/index')

Page({
  data: {
    stats: {
      todayOrders: 0,
      totalEarnings: 0,
      rating: 0
    },
    pendingOrders: []
  },

  onLoad() {
    this.fetchStats()
    this.fetchPendingOrders()
  },

  onShow() {
    this.fetchPendingOrders()
  },

  fetchStats() {
    var self = this
    getCompanionStats()
      .then(function (res) {
        var data = res.data || res
        self.setData({
          stats: {
            todayOrders: data.today_orders || 0,
            totalEarnings: data.total_earnings || 0,
            rating: data.avg_rating || 0
          }
        })
      })
      .catch(function (err) {
        console.error('获取统计失败', err)
      })
  },

  fetchPendingOrders() {
    getOrders({ status: 'created', page: 1, page_size: 5 })
      .then(res => {
        const list = res.data && res.data.items ? res.data.items : (res.data || [])
        this.setData({ pendingOrders: list })
      })
      .catch(err => {
        console.error('获取待接单列表失败', err)
      })
  },

  onViewAllPending() {
    wx.navigateTo({
      url: '/pages/companion/available-orders/index'
    })
  },

  onOrderTap(e) {
    const id = e.currentTarget.dataset.id
    wx.navigateTo({
      url: '/pages/companion/order-detail/index?id=' + id
    })
  }
})
