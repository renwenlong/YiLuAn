const router = require('../../../utils/router')
const i18nBehavior = require('../../../behaviors/i18n')
Page({
  behaviors: [i18nBehavior],
  data: {
    i18nScopes: ['common', 'profile'],
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
