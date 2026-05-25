const router = require('../../../utils/router')
const analytics = require('../../../utils/analytics')
Page({
  data: {
    status: 'success', // 'success' | 'fail' | 'cancel'
    orderId: '',
    errorMsg: ''
  },

  onLoad(options) {
    this.setData({
      status: options.status || 'success',
      orderId: options.order_id || '',
      errorMsg: options.msg ? decodeURIComponent(options.msg) : ''
    })
    // [funnel-5] 支付成功 — 仅在 success 落地时计一次漏斗终点
    var status = options.status || 'success'
    if (status === 'success') {
      try { analytics.trackFunnel(analytics.FUNNEL_STEPS.PAYMENT_SUCCESS, { order_id: options.order_id ? String(options.order_id) : undefined }) } catch (_) {}
    }
  },

  onViewOrder() {
    if (this.data.orderId) {
      router.redirect({
        url: '/pages/patient/order-detail/index?id=' + this.data.orderId
      })
    } else {
      router.relaunch({ url: '/pages/orders/index' })
    }
  },

  onRetry() {
    if (this.data.orderId) {
      router.redirect({
        url: '/pages/patient/order-detail/index?id=' + this.data.orderId + '&need_pay=1'
      })
    }
  },

  onGoHome() {
    router.relaunch({ url: '/pages/patient/home/index' })
  }
})
