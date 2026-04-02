const { getOrders } = require('../../services/order')
const { ORDER_STATUS } = require('../../utils/constants')
const store = require('../../store/index')

Page({
  data: {
    tabs: ['全部', '待接单', '进行中', '已完成', '已取消'],
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
      1: 'created',
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
        console.error('获取订单列表失败', err)
        wx.showToast({ title: '加载失败', icon: 'none' })
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
    const role = store.getState().user && store.getState().user.role
    const detailPage = role === 'companion'
      ? '/pages/companion/order-detail/index?id='
      : '/pages/patient/order-detail/index?id='
    wx.navigateTo({
      url: detailPage + id
    })
  }
})
