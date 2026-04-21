// [B4]: 用户协议元信息动态绑定，权威源：config/legal.js
const { TERMS_UPDATED_AT, TERMS_EFFECTIVE_AT, TERMS_VERSION } = require('../../../config/legal')

Page({
  data: {
    showBackTop: false,
    scrollToTop: false,
    updatedAt: TERMS_UPDATED_AT,
    effectiveAt: TERMS_EFFECTIVE_AT,
    version: TERMS_VERSION
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
