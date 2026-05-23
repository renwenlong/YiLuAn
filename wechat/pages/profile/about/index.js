const router = require('../../../utils/router')
Page({
  data: {
    version: '__APP_VERSION__',
    gitSha: '__GIT_SHA__',
    buildTime: '__BUILD_TIME__'
  },

  onUserAgreement: function () {
    router.navigate({ url: '/pages/legal/terms/index' })
  },

  onPrivacyPolicy: function () {
    router.navigate({ url: '/pages/legal/privacy/index' })
  }
})
