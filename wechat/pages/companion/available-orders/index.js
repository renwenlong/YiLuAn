const { getOrders, orderAction } = require('../../../services/order')
const store = require('../../../store/index')
const router = require('../../../utils/router')
const { formatDate } = require('../../../utils/format')
const i18n = require('../../../utils/i18n')
const i18nBehavior = require('../../../behaviors/i18n')

Page({
  behaviors: [i18nBehavior],
  data: {
    i18nScopes: ['common', 'availableOrders'],
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
      wx.showToast({ title: i18n.t('availableOrders.loadFailed'), icon: 'none' })
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
        title: i18n.t('availableOrders.bindPhoneTitle'),
        content: i18n.t('availableOrders.bindPhoneContent'),
        confirmText: i18n.t('availableOrders.bindPhoneConfirm'),
        success: function (res) {
          if (res.confirm) {
            router.navigate({
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
      title: i18n.t('availableOrders.acceptTitle'),
      content: i18n.t('availableOrders.acceptContent'),
      confirmText: i18n.t('availableOrders.acceptConfirm'),
      confirmColor: '#4CAF50'
    })
    if (!res.confirm) return

    this.setData({ loading: true })
    try {
      await orderAction(id, 'accept')
      wx.showToast({ title: i18n.t('availableOrders.acceptSuccess'), icon: 'success' })
      setTimeout(() => {
        router.redirect({
          url: `/pages/companion/order-detail/index?id=${id}`
        })
      }, 1000)
    } catch (err) {
      wx.showToast({ title: i18n.t('availableOrders.acceptFailed'), icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  onOrderTap(e) {
    const { id } = e.currentTarget.dataset
    router.navigate({
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
