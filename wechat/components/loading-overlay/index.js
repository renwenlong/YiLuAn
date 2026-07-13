const i18nBehavior = require('../../behaviors/i18n')

Component({
  behaviors: [i18nBehavior],
  data: {
    i18nScopes: ['common']
  },
  properties: {
    show: {
      type: Boolean,
      value: false
    }
  }
})
