Page({
  data: {
    showBackTop: false,
    scrollToTop: false
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
