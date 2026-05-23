const router = require('../../../utils/router')
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
