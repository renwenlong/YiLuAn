const { ORDER_STATUS, SERVICE_TYPES } = require('../../utils/constants')

Component({
  properties: {
    order: {
      type: Object,
      value: {}
    }
  },

  data: {
    statusInfo: {},
    serviceLabel: ''
  },

  observers: {
    'order': function (val) {
      if (!val) return
      var statusInfo = ORDER_STATUS[val.status] || { label: '未知', color: '#999' }
      var serviceType = SERVICE_TYPES[val.service_type] || {}
      this.setData({
        statusInfo: statusInfo,
        serviceLabel: serviceType.label || ''
      })
    }
  },

  methods: {
    onTap: function () {
      this.triggerEvent('tap', { id: this.data.order.id })
    }
  }
})
