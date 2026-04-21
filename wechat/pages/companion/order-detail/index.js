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
    // 前置：手机号未绑定 → 弹窗 + 跳转绑定页
    var state = store.getState()
    var u = (state && state.user) || {}
    if (!u.phone) {
      var orderId = this.orderId
      wx.showModal({
        title: '请先绑定手机号',
        content: '接单前需要绑定手机号，方便患者联系您',
        confirmText: '去绑定',
        success: function (res) {
          if (res.confirm) {
            wx.navigateTo({
              url: '/pages/profile/bind-phone/index?redirect='
                + encodeURIComponent('/pages/companion/order-detail/index?id=' + orderId)
            })
          }
        }
      })
      return
    }

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
  },

  async onReject() {
    const res = await wx.showModal({
      title: '确认拒单',
      content: '拒绝后订单将取消，已支付的款项将退还给患者。确定要拒绝吗？',
      confirmText: '确认拒绝',
      confirmColor: '#e53935'
    })
    if (!res.confirm) return

    this.setData({ loading: true })
    try {
      await orderAction(this.orderId, 'reject')
      wx.showToast({ title: '已拒绝', icon: 'success' })
      this.loadOrder()
    } catch (err) {
      var msg = '操作失败'
      if (err && err.data && err.data.detail) msg = err.data.detail
      wx.showToast({ title: msg, icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  async onCancelAccepted() {
    const res = await wx.showModal({
      title: '确认取消',
      content: '取消后订单将退款给患者，确定要取消吗？',
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
  }
})
