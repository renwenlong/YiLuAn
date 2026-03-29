const { getOrders } = require('../../../services/order')
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
    // TODO: replace with actual stats API
    const state = store.getState()
    if (state && state.companionStats) {
      this.setData({ stats: state.companionStats })
    }
  },

  fetchPendingOrders() {
    getOrders({ status: 'pending', page: 1, page_size: 5 })
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
