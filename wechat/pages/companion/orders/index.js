const router = require('../../../utils/router')
const { getOrders } = require('../../../services/order')
const logger = require('../../../utils/logger')
const i18n = require('../../../utils/i18n')
const i18nBehavior = require('../../../behaviors/i18n')

Page({
  behaviors: [i18nBehavior],
  data: {
    i18nScopes: ['order'],
    tabs: [
      i18n.t('order.tabAll'),
      i18n.t('order.tabAccepted'),
      i18n.t('order.tabInProgress'),
      i18n.t('order.tabCompleted'),
      i18n.t('order.tabCancelled')
    ],
    activeTab: 0,
    orders: [],
    page: 1,
    hasMore: true,
    loading: false
  },

  onLoad() {
    this.loadOrders()
  },

  onShow() {
    this.setData({ page: 1, orders: [], hasMore: true })
    this.loadOrders()
  },

  onTabChange(e) {
    const index = e.currentTarget.dataset.index
    this.setData({
      activeTab: index,
      page: 1,
      orders: [],
      hasMore: true
    })
    this.loadOrders()
  },

  loadOrders() {
    if (this.data.loading || !this.data.hasMore) return
    this.setData({ loading: true })

    const statusMap = {
      0: undefined,
      1: 'accepted',
      2: 'in_progress',
      3: 'completed',
      4: 'cancelled'
    }
    const status = statusMap[this.data.activeTab]
    const params = {
      page: this.data.page,
      page_size: 10
    }
    if (status) {
      params.status = status
    }

    getOrders(params)
      .then(res => {
        const list = res.items || []
        const hasMore = list.length >= 10
        this.setData({
          orders: this.data.orders.concat(list),
          hasMore: hasMore,
          page: this.data.page + 1
        })
      })
      .catch(err => {
        logger.error('获取订单列表失败', { err: err && (err.message || String(err)) })
        wx.showToast({ title: i18n.t('order.loadFailed'), icon: 'none' })
      })
      .finally(() => {
        this.setData({ loading: false })
      })
  },

  onReachBottom() {
    this.loadOrders()
  },

  onPullDownRefresh() {
    this.setData({ page: 1, orders: [], hasMore: true })
    this.loadOrders()
    wx.stopPullDownRefresh()
  },

  onOrderTap(e) {
    const id = e.currentTarget.dataset.id
    router.navigate({
      url: '/pages/companion/order-detail/index?id=' + id
    })
  }
})
