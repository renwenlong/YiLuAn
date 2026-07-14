const { getOrderDetail, orderAction } = require('../../../services/order')
const { getOrderReview } = require('../../../services/review')
const store = require('../../../store/index')
const router = require('../../../utils/router')
const { ORDER_STATUS, SERVICE_TYPES } = require('../../../utils/constants')
const { formatPrice, formatDate } = require('../../../utils/format')
const i18n = require('../../../utils/i18n')
const i18nBehavior = require('../../../behaviors/i18n')

Page({
  behaviors: [i18nBehavior],
  data: {
    i18nScopes: ['common', 'orderDetail', 'companionOrderDetail', 'serviceType', 'orderStatus'],
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
      // S2-REQ-003-P5b: 优先 order.service_name_snapshot (P3 快照)，
      // fallback SERVICE_TYPES dict 兼容历史订单。
      const svc = SERVICE_TYPES[order.service_type] || {}
      const serviceLabel = order.service_name_snapshot || svc.label || order.service_type

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
          // S2-REQ-003-P5b fix: 显式优先 servicePriceSnapshot (P3 后 order.price = snapshot)
          formattedPrice: order.service_price_snapshot
            ? formatPrice(order.service_price_snapshot)
            : (order.price ? formatPrice(order.price) : ''),
          timelineIndex: order.timeline_index
        },
        serviceLabel: serviceLabel
      })
    } catch (err) {
      wx.showToast({ title: i18n.t('orderDetail.loadFailed'), icon: 'none' })
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
        title: i18n.t('companionOrderDetail.bindPhoneTitle'),
        content: i18n.t('companionOrderDetail.bindPhoneContent'),
        confirmText: i18n.t('companionOrderDetail.bindPhoneConfirm'),
        success: function (res) {
          if (res.confirm) {
            router.navigate({
              url: '/pages/profile/bind-phone/index?redirect='
                + encodeURIComponent('/pages/companion/order-detail/index?id=' + orderId)
            })
          }
        }
      })
      return
    }

    var order = this.data.order
    var content = i18n.t('companionOrderDetail.acceptConfirmDefault')
    if (order && order.payment_status === 'unpaid') {
      content = i18n.t('companionOrderDetail.acceptConfirmUnpaid')
    }
    const res = await wx.showModal({
      title: i18n.t('companionOrderDetail.confirmAcceptTitle'),
      content: content,
      confirmText: i18n.t('common.confirm'),
      confirmColor: '#4CAF50'
    })
    if (!res.confirm) return

    this.setData({ loading: true })
    try {
      await orderAction(this.orderId, 'accept')
      wx.showToast({ title: i18n.t('companionOrderDetail.acceptSuccess'), icon: 'success' })
      this.loadOrder()
    } catch (err) {
      wx.showToast({ title: i18n.t('orderDetail.opFailed'), icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  async onStart() {
    const res = await wx.showModal({
      title: i18n.t('companionOrderDetail.notifyPatientTitle'),
      content: i18n.t('companionOrderDetail.notifyStartContent'),
      confirmText: i18n.t('companionOrderDetail.notifyStartConfirm'),
      confirmColor: '#4CAF50'
    })
    if (!res.confirm) return

    this.setData({ loading: true })
    try {
      await orderAction(this.orderId, 'request-start')
      wx.showToast({ title: i18n.t('companionOrderDetail.notifiedWaiting'), icon: 'success' })
    } catch (err) {
      wx.showToast({ title: i18n.t('orderDetail.opFailed'), icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  async onComplete() {
    const res = await wx.showModal({
      title: i18n.t('companionOrderDetail.completeTitle'),
      content: i18n.t('companionOrderDetail.completeContent'),
      confirmText: i18n.t('companionOrderDetail.completeConfirm'),
      confirmColor: '#4CAF50'
    })
    if (!res.confirm) return

    this.setData({ loading: true })
    try {
      await orderAction(this.orderId, 'complete')
      wx.showToast({ title: i18n.t('companionOrderDetail.serviceCompleted'), icon: 'success' })
      this.loadOrder()
    } catch (err) {
      wx.showToast({ title: i18n.t('orderDetail.opFailed'), icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  onChat() {
    router.navigate({
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
      title: i18n.t('companionOrderDetail.rejectTitle'),
      content: i18n.t('companionOrderDetail.rejectContent'),
      confirmText: i18n.t('companionOrderDetail.rejectConfirm'),
      confirmColor: '#e53935'
    })
    if (!res.confirm) return

    this.setData({ loading: true })
    try {
      await orderAction(this.orderId, 'reject')
      wx.showToast({ title: i18n.t('companionOrderDetail.rejected'), icon: 'success' })
      this.loadOrder()
    } catch (err) {
      var msg = i18n.t('orderDetail.opFailed')
      if (err && err.data && err.data.detail) msg = err.data.detail
      wx.showToast({ title: msg, icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  async onCancelAccepted() {
    const res = await wx.showModal({
      title: i18n.t('companionOrderDetail.cancelAcceptedTitle'),
      content: i18n.t('companionOrderDetail.cancelAcceptedContent'),
      confirmText: i18n.t('companionOrderDetail.cancelAcceptedConfirm'),
      confirmColor: '#e53935'
    })
    if (!res.confirm) return

    this.setData({ loading: true })
    try {
      await orderAction(this.orderId, 'cancel')
      wx.showToast({ title: i18n.t('orderDetail.cancelled'), icon: 'success' })
      this.loadOrder()
    } catch (err) {
      wx.showToast({ title: i18n.t('orderDetail.opFailed'), icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  }
})
