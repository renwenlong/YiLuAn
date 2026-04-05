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
          formattedPrice: order.price ? formatPrice(order.price) : '',
          timelineIndex: order.timeline_index
        },
        serviceLabel: svc.label || order.service_type
      })
    } catch (err) {
      wx.showToast({ title: '加载失败', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  async onAccept() {
    var order = this.data.order
    var content = '确定要接受该订单吗？'
    if (order && order.payment_status === 'unpaid') {
      content = '患者暂未支付，是否仍要接单？'
    }
    const res = await wx.showModal({
      title: '确认接单',
      content: content,
      confirmText: '确认',
      confirmColor: '#4CAF50'
    })
    if (!res.confirm) return

    this.setData({ loading: true })
    try {
      await orderAction(this.orderId, 'accept')
      wx.showToast({ title: '接单成功', icon: 'success' })
      this.loadOrder()
    } catch (err) {
      wx.showToast({ title: '操作失败', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  async onStart() {
    const res = await wx.showModal({
      title: '通知患者',
      content: '将通知患者确认开始服务，患者确认后服务正式开始',
      confirmText: '确认通知',
      confirmColor: '#4CAF50'
    })
    if (!res.confirm) return

    this.setData({ loading: true })
    try {
      await orderAction(this.orderId, 'request-start')
      wx.showToast({ title: '已通知患者，等待确认', icon: 'success' })
    } catch (err) {
      wx.showToast({ title: '操作失败', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  async onComplete() {
    const res = await wx.showModal({
      title: '完成服务',
      content: '确认已完成本次陪诊服务？',
      confirmText: '确认完成',
      confirmColor: '#4CAF50'
    })
    if (!res.confirm) return

    this.setData({ loading: true })
    try {
      await orderAction(this.orderId, 'complete')
      wx.showToast({ title: '服务已完成', icon: 'success' })
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

  onCallPatient() {
    const { order } = this.data
    if (order && order.patient && order.patient.phone) {
      wx.makePhoneCall({ phoneNumber: order.patient.phone })
    }
  }
})
