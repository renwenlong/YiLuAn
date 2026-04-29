const { ORDER_STATUS, SERVICE_TYPES } = require('../../utils/constants')
const { formatCurrency } = require('../../utils/formatCurrency')

Component({
  properties: {
    order: {
      type: Object,
      value: {}
    }
  },

  data: {
    statusInfo: {},
    serviceLabel: '',
    priceText: '¥0.00'
  },

  observers: {
    'order': function (val) {
      if (!val) return
      var statusInfo = ORDER_STATUS[val.status] || { label: '未知', color: '#999' }
      var serviceType = SERVICE_TYPES[val.service_type] || {}
      this.setData({
        statusInfo: statusInfo,
        serviceLabel: serviceType.label || '',
        priceText: formatCurrency(val.price)
      })
    }
  },

  methods: {
    onTap: function () {
      this.triggerEvent('tap', { id: this.data.order.id })
    }
  }
})
