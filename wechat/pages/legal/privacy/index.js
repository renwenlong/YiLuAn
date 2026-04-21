// A21-06: \u9690\u79c1\u534f\u8bae\u201c\u6700\u8fd1\u66f4\u65b0\u65f6\u95f4\u201d\u52a8\u6001\u7ed1\u5b9a\uff0c\u6743\u5a01\u6e90\uff1aconfig/privacy.js
const { PRIVACY_UPDATED_AT, PRIVACY_EFFECTIVE_AT } = require('../../../config/privacy')

Page({
  data: {
    showBackTop: false,
    scrollToTop: false,
    updatedAt: PRIVACY_UPDATED_AT,
    effectiveAt: PRIVACY_EFFECTIVE_AT
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
