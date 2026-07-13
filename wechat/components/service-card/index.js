const { SERVICE_TYPES } = require('../../utils/constants')
const { formatCurrency } = require('../../utils/formatCurrency')
const i18n = require('../../utils/i18n')
const i18nBehavior = require('../../behaviors/i18n')

Component({
  behaviors: [i18nBehavior],
  data: {
    i18nScopes: ['serviceType'],
    info: {},
    label: '',
    desc: '',
    priceText: '¥0.00'
  },

  properties: {
    type: {
      type: String,
      value: ''
    },
    active: {
      type: Boolean,
      value: false
    }
  },

  observers: {
    'type': function (val) {
      if (val && SERVICE_TYPES[val]) {
        var info = SERVICE_TYPES[val]
        this.setData({
          info: info,
          label: i18n.t('serviceType.' + val),
          desc: i18n.t('serviceType.' + val + 'Desc'),
          priceText: formatCurrency(info.price)
        })
      }
    }
  }
})
