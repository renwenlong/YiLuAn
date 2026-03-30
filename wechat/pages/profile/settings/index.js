Page({
  data: {
    cacheSize: '0 KB'
  },

  onLoad: function () {
    this.calcCache()
  },

  calcCache: function () {
    var info = wx.getStorageInfoSync()
    this.setData({ cacheSize: (info.currentSize || 0) + ' KB' })
  },

  onClearCache: function () {
    var self = this
    wx.showModal({
      title: '提示',
      content: '确定清除缓存？',
      success: function (res) {
        if (res.confirm) {
          wx.clearStorageSync()
          self.setData({ cacheSize: '0 KB' })
          wx.showToast({ title: '已清除', icon: 'success' })
        }
      }
    })
  },

  onAbout: function () {
    wx.navigateTo({ url: '/pages/profile/about/index' })
  }
})
