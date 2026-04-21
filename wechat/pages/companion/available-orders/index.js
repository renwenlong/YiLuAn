const { getOrders, orderAction } = require('../../../services/order')
const store = require('../../../store/index')
const { formatDate } = require('../../../utils/format')

Page({
  data: {
    orders: [],
    page: 1,
    hasMore: true,
    loading: false
  },

  onLoad() {
    this.loadOrders()
  },

  onShow() {
    if (this.data.orders.length > 0) {
      this.setData({ page: 1, orders: [], hasMore: true })
      this.loadOrders()
    }
  },

  async loadOrders() {
    if (this.data.loading || !this.data.hasMore) return
    this.setData({ loading: true })
    try {
      const res = await getOrders({
        status: 'created',
        page: this.data.page,
        page_size: 10
      })
      const list = res.items ? res.items : (res.data && res.data.items ? res.data.items : (res.list || res.data || []))
      const newOrders = list.map(order => ({
        ...order,
        formattedDate: formatDate(order.appointment_date)
      }))
      this.setData({
        orders: this.data.page === 1 ? newOrders : [...this.data.orders, ...newOrders],
        hasMore: newOrders.length >= 10,
        page: this.data.page + 1
      })
    } catch (err) {
      wx.showToast({ title: '加载失败', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  async onAccept(e) {
    // 前置：手机号未绑定 → 弹窗 + 跳转绑定页（后端也会拦，这里走体验提前）
    var state = store.getState()
    var user = (state && state.user) || {}
    if (!user.phone) {
      wx.showModal({
        title: '请先绑定手机号',
        content: '接单前需要绑定手机号，方便患者联系您',
        confirmText: '去绑定',
        success: function (res) {
          if (res.confirm) {
            wx.navigateTo({
              url: '/pages/profile/bind-phone/index?redirect='
                + encodeURIComponent('/pages/companion/available-orders/index')
            })
          }
        }
      })
      return
    }

    const { id } = e.currentTarget.dataset
    const res = await wx.showModal({
      title: '确认接单',
      content: '确定要接受该订单吗？',
      confirmText: '确认接单',
      confirmColor: '#4CAF50'
    })
    if (!res.confirm) return

    this.setData({ loading: true })
    try {
      await orderAction(id, 'accept')
      wx.showToast({ title: '接单成功', icon: 'success' })
      setTimeout(() => {
        wx.redirectTo({
          url: `/pages/companion/order-detail/index?id=${id}`
        })
      }, 1000)
    } catch (err) {
      wx.showToast({ title: '接单失败', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  onOrderTap(e) {
    const { id } = e.currentTarget.dataset
    wx.navigateTo({
      url: `/pages/companion/order-detail/index?id=${id}`
    })
  },

  onReachBottom() {
    this.loadOrders()
  },

  onPullDownRefresh() {
    this.setData({ page: 1, orders: [], hasMore: true })
    this.loadOrders().then(() => {
      wx.stopPullDownRefresh()
    })
  }
})
