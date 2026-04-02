const { getOrders } = require('../../../services/order')

Page({
  data: {
    orders: [],
    loading: false
  },

  onLoad() {
    this.loadOrders()
  },

  onShow() {
    if (this.data.orders.length > 0) {
      this.loadOrders()
    }
  },

  async loadOrders() {
    if (this.data.loading) return
    this.setData({ loading: true })
    try {
      const [acceptedRes, progressRes] = await Promise.all([
        getOrders({ status: 'accepted', page: 1, page_size: 50 }),
        getOrders({ status: 'in_progress', page: 1, page_size: 50 })
      ])
      const accepted = acceptedRes.items || []
      const inProgress = progressRes.items || []
      this.setData({ orders: [...inProgress, ...accepted] })
    } catch (err) {
      wx.showToast({ title: '加载失败', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  onOrderTap(e) {
    const { id } = e.currentTarget.dataset
    wx.navigateTo({
      url: '/pages/companion/order-detail/index?id=' + id
    })
  },

  onPullDownRefresh() {
    this.loadOrders().then(() => {
      wx.stopPullDownRefresh()
    })
  }
})
