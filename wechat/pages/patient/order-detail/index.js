const { getOrderDetail, orderAction, payOrder, requestWechatPayment } = require('../../../services/order')
const { getOrderReview } = require('../../../services/review')
const {
  listEmergencyContacts,
  getEmergencyHotline,
  triggerEmergencyEvent,
} = require('../../../services/emergency')
const store = require('../../../store/index')
const { ORDER_STATUS, SERVICE_TYPES } = require('../../../utils/constants')
const { formatPrice, formatDate } = require('../../../utils/format')
const { isCountdownUrgent } = require('../../../utils/countdown')

const PAYMENT_STATUS_MAP = {
  unpaid: '待支付',
  paid: '已支付',
  refunded: '已退款'
}

Page({
  data: {
    order: null,
    loading: true,
    // AI-9: 操作锁，防止状态切换瞬间用户重复点击
    actionLoading: false,
    statusList: ORDER_STATUS,
    serviceLabel: '',
    paymentStatusLabel: '',
    paymentStatusClass: '',
    countdown: '',
    countdownUrgent: false,
    // [F-03] Emergency call
    showEmergency: false,
    emergencyContacts: [],
    emergencyHotline: ''
  },

  onLoad(options) {
    this.orderId = options.id
    this.needPay = options.need_pay === '1'
    this.loadOrder()
  },

  onShow() {
    if (this.orderId && !this.data.loading) {
      this.loadOrder()
    }
  },

  onHide() {
    this._clearCountdown()
  },

  onUnload() {
    this._clearCountdown()
  },

  _clearCountdown() {
    if (this._countdownTimer) {
      clearInterval(this._countdownTimer)
      this._countdownTimer = null
    }
  },

  _startCountdown(expiresAt) {
    this._clearCountdown()
    if (!expiresAt) return

    var self = this
    var expTime = new Date(expiresAt).getTime()

    function update() {
      var now = Date.now()
      var diff = expTime - now
      if (diff <= 0) {
        self.setData({ countdown: '已超时', countdownUrgent: false })
        self._clearCountdown()
        self.loadOrder()
        return
      }
      var hours = Math.floor(diff / 3600000)
      var minutes = Math.floor((diff % 3600000) / 60000)
      self.setData({
        countdown: hours + '小时' + minutes + '分钟',
        countdownUrgent: isCountdownUrgent(diff)
      })
    }

    update()
    this._countdownTimer = setInterval(update, 60000)
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

      var paymentStatus = order.payment_status || 'unpaid'
      this.setData({
        order: {
          ...order,
          review: review,
          formattedDate: formatDate(order.appointment_date),
          formattedPrice: order.price ? formatPrice(order.price) : '',
          timelineIndex: order.timeline_index
        },
        serviceLabel: svc.label || order.service_type,
        paymentStatusLabel: PAYMENT_STATUS_MAP[paymentStatus] || paymentStatus,
        paymentStatusClass: paymentStatus
      })

      // Start countdown if order is created and has expires_at
      if (order.status === 'created' && order.expires_at) {
        this._startCountdown(order.expires_at)
      } else {
        this._clearCountdown()
      }

      // Auto-trigger payment prompt after order creation
      if (this.needPay && paymentStatus === 'unpaid') {
        this.needPay = false
        this.onPay()
      }
    } catch (err) {
      wx.showToast({ title: '加载失败', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  async onPay() {
    var order = this.data.order
    var priceText = order.formattedPrice || ('¥' + order.price)
    const res = await wx.showModal({
      title: '确认支付',
      content: '支付 ' + priceText,
      confirmText: '确认支付',
      confirmColor: '#4CAF50'
    })
    if (!res.confirm) return

    if (this.data.actionLoading) return
    this.setData({ actionLoading: true })
    try {
      // Step 1: Create prepay order on backend
      var payResult = await payOrder(this.orderId)

      // Step 2: Call wx.requestPayment (skipped for mock provider)
      await requestWechatPayment(payResult)

      // Step 3: Navigate to pay-result page on success
      wx.redirectTo({
        url: '/pages/patient/pay-result/index?status=success&order_id=' + this.orderId
      })
    } catch (err) {
      if (err && err.cancelled) {
        // User cancelled payment
        wx.redirectTo({
          url: '/pages/patient/pay-result/index?status=cancel&order_id=' + this.orderId
        })
      } else {
        // Payment failed
        var msg = '支付失败'
        if (err && err.data && err.data.detail) msg = err.data.detail
        if (err && err.errMsg) msg = err.errMsg
        wx.redirectTo({
          url: '/pages/patient/pay-result/index?status=fail&order_id=' + this.orderId + '&msg=' + encodeURIComponent(msg)
        })
      }
    } finally {
      this.setData({ actionLoading: false })
    }
  },

  async onConfirmStart() {
    const res = await wx.showModal({
      title: '确认开始服务',
      content: '确认后服务正式开始，如需取消将退还50%费用',
      confirmText: '确认开始',
      confirmColor: '#4CAF50'
    })
    if (!res.confirm) return

    if (this.data.actionLoading) return
    this.setData({ actionLoading: true })
    try {
      await orderAction(this.orderId, 'confirm-start')
      wx.showToast({ title: '服务已开始', icon: 'success' })
      this.loadOrder()
    } catch (err) {
      var msg = '操作失败'
      if (err && err.data && err.data.detail) msg = err.data.detail
      wx.showToast({ title: msg, icon: 'none' })
    } finally {
      this.setData({ actionLoading: false })
    }
  },

  async onCancel() {
    var order = this.data.order
    var content = '确定要取消该订单吗？'
    if (order.payment_status === 'paid') {
      content = '取消后将全额退款，确定要取消吗？'
    }
    const res = await wx.showModal({
      title: '确认取消',
      content: content,
      confirmText: '确认取消',
      confirmColor: '#e53935'
    })
    if (!res.confirm) return

    if (this.data.actionLoading) return
    this.setData({ actionLoading: true })
    try {
      await orderAction(this.orderId, 'cancel')
      wx.showToast({ title: '已取消', icon: 'success' })
      this.loadOrder()
    } catch (err) {
      wx.showToast({ title: '操作失败', icon: 'none' })
    } finally {
      this.setData({ actionLoading: false })
    }
  },

  async onCancelInProgress() {
    var order = this.data.order
    var content = '服务已开始，取消将退还50%费用，确定要取消吗？'
    const res = await wx.showModal({
      title: '确认取消',
      content: content,
      confirmText: '确认取消',
      confirmColor: '#e53935'
    })
    if (!res.confirm) return

    if (this.data.actionLoading) return
    this.setData({ actionLoading: true })
    try {
      await orderAction(this.orderId, 'cancel')
      wx.showToast({ title: '已取消', icon: 'success' })
      this.loadOrder()
    } catch (err) {
      wx.showToast({ title: '操作失败', icon: 'none' })
    } finally {
      this.setData({ actionLoading: false })
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
  },

  onReorder() {
    const { order } = this.data
    if (!order) return
    wx.navigateTo({
      url: '/pages/patient/create-order/index?hospital_id=' + order.hospital_id +
        '&service_type=' + order.service_type
    })
  },

  // [F-03] Emergency call ----------------------------------------------
  async onEmergencyTap() {
    this.setData({ showEmergency: true })
    try {
      const [contacts, hotline] = await Promise.all([
        listEmergencyContacts().catch(() => []),
        getEmergencyHotline().catch(() => ({ hotline: '' })),
      ])
      this.setData({
        emergencyContacts: contacts || [],
        emergencyHotline: (hotline && hotline.hotline) || '',
      })
    } catch (e) {
      // surface but keep panel open with whatever loaded
    }
  },

  onEmergencyClose() {
    this.setData({ showEmergency: false })
  },

  async onCallContact(e) {
    const { id } = e.currentTarget.dataset
    await this._fireEmergency({ contact_id: id })
  },

  async onCallHotline() {
    await this._fireEmergency({ hotline: true })
  },

  onManageContacts() {
    this.setData({ showEmergency: false })
    wx.navigateTo({ url: '/pages/profile/emergency-contacts/index' })
  },

  async _fireEmergency(target) {
    var payload = Object.assign({ order_id: this.orderId }, target)
    try {
      const result = await triggerEmergencyEvent(payload)
      this.setData({ showEmergency: false })
      if (result && result.phone_to_call) {
        wx.makePhoneCall({ phoneNumber: result.phone_to_call })
      }
    } catch (err) {
      var msg = '呼叫失败'
      if (err && err.data && err.data.detail) {
        var d = err.data.detail
        msg = (d && d.message) || (typeof d === 'string' ? d : msg)
      }
      wx.showToast({ title: msg, icon: 'none' })
    }
  }
})
