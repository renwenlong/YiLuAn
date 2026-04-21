// A21-06 + [B4]: 隐私协议元信息动态绑定，权威源：config/legal.js
const { PRIVACY_UPDATED_AT, PRIVACY_EFFECTIVE_AT, PRIVACY_VERSION } = require('../../../config/legal')

Page({
  data: {
    showBackTop: false,
    scrollToTop: false,
    updatedAt: PRIVACY_UPDATED_AT,
    effectiveAt: PRIVACY_EFFECTIVE_AT,
    version: PRIVACY_VERSION
  },

  onPageScroll: function (e) {
    var show = e.detail.scrollTop > 500
    if (show !== this.data.showBackTop) {
      this.setData({ showBackTop: show })
    }
  },

  onBackToTop: function () {
    this.setData({ scrollToTop: true })
    var self = this
    setTimeout(function () {
      self.setData({ scrollToTop: false })
    }, 50)
  }
})
