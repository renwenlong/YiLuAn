Page({
  data: {
    version: '__APP_VERSION__',
    gitSha: '__GIT_SHA__',
    buildTime: '__BUILD_TIME__'
  },

  onUserAgreement: function () {
    wx.navigateTo({ url: '/pages/legal/terms/index' })
  },

  onPrivacyPolicy: function () {
    wx.navigateTo({ url: '/pages/legal/privacy/index' })
  }
})
