const { SERVICE_TYPES } = require('../../utils/constants')
const { formatCurrency } = require('../../utils/formatCurrency')

Component({
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

  data: {
    info: {},
    priceText: '¥0.00'
  },

  observers: {
    'type': function (val) {
      if (val && SERVICE_TYPES[val]) {
        var info = SERVICE_TYPES[val]
        this.setData({ info: info, priceText: formatCurrency(info.price) })
      }
    }
  }
})
