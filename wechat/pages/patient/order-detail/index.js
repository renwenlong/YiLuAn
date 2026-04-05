const { getOrderDetail, orderAction } = require('../../../services/order')
const { getOrderReview } = require('../../../services/review')
const store = require('../../../store/index')
const { ORDER_STATUS, SERVICE_TYPES } = require('../../../utils/constants')
const { formatPrice, formatDate } = require('../../../utils/format')

Page({
  data: {
    order: null,
    loading: true,
    statusList: ORDER_STATUS,
    serviceLabel: ''
  },

  onLoad(options) {
    this.orderId = options.id
    this.loadOrder()
  },

  onShow() {
    if (this.orderId && !this.data.loading) {
      this.loadOrder()
    }
  },

  async loadOrder() {
    this.setData({ loading: true })
    try {
      const order = await getOrderDetail(this.orderId)
      const svc = SERVICE_TYPES[order.service_type] || {}

      var review = null
      if (order.status === 'reviewed' || order.status === 'completed') {
        try {
          review = await getOrderReview(this.orderId)
        } catch (e) {
          // 404 = no review yet
        }
      }

      this.setData({
        order: {
          ...order,
          review: review,
          formattedDate: formatDate(order.appointment_date),
          formattedPrice: order.price ? formatPrice(order.price) : ''
        },
        serviceLabel: svc.label || order.service_type
      })
    } catch (err) {
      wx.showToast({ title: '加载失败', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  async onCancel() {
    const res = await wx.showModal({
      title: '确认取消',
      content: '确定要取消该订单吗？',
      confirmText: '确认取消',
      confirmColor: '#e53935'
    })
    if (!res.confirm) return

    this.setData({ loading: true })
    try {
      await orderAction(this.orderId, 'cancel')
      wx.showToast({ title: '已取消', icon: 'success' })
      this.loadOrder()
    } catch (err) {
      wx.showToast({ title: '操作失败', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  onChat() {
    wx.navigateTo({
      url: `/pages/chat/room/index?id=${this.orderId}`
    })
  },

  onReview() {
    wx.navigateTo({
      url: `/pages/review/write/index?id=${this.orderId}`
    })
  },

  onCallCompanion() {
    const { order } = this.data
    if (order && order.companion && order.companion.phone) {
      wx.makePhoneCall({ phoneNumber: order.companion.phone })
    }
  }
})
