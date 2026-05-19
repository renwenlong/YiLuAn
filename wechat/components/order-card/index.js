const { ORDER_STATUS, SERVICE_TYPES } = require('../../utils/constants')
const { formatCurrency } = require('../../utils/formatCurrency')
const { relationLabel } = require('../../utils/familyRelation')

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
    priceText: '¥0.00',
    familyMemberText: ''
  },

  observers: {
    'order': function (val) {
      if (!val) return
      var statusInfo = ORDER_STATUS[val.status] || { label: '未知', color: '#999' }
      var serviceType = SERVICE_TYPES[val.service_type] || {}
      var famText = ''
      if (val.family_member && val.family_member.name) {
        famText = val.family_member.name + '（' + relationLabel(val.family_member.relation) + '）'
      }
      this.setData({
        statusInfo: statusInfo,
        serviceLabel: serviceType.label || '',
        priceText: formatCurrency(val.price),
        familyMemberText: famText
      })
    }
  },

  methods: {
    onTap: function () {
      this.triggerEvent('tap', { id: this.data.order.id })
    }
  }
})
