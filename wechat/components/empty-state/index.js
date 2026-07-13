// P-07: 统一空状态组件，新增 hint 属性以兼容 chat / orders / 钱包等场景
const i18n = require('../../utils/i18n')

Component({
  properties: {
    text: {
      type: String,
      value: i18n.t('emptyState.defaultText')
    },
    hint: {
      type: String,
      value: ''
    },
    icon: {
      type: String,
      value: i18n.t('emptyState.defaultIcon')
    }
  }
})
