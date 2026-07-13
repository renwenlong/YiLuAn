const { ORDER_STATUS, SERVICE_TYPES } = require('../../utils/constants')
const { formatCurrency } = require('../../utils/formatCurrency')
const { relationLabelI18n: relationLabel } = require('../../utils/familyRelation')
const i18n = require('../../utils/i18n')
const i18nBehavior = require('../../behaviors/i18n')

Component({
  behaviors: [i18nBehavior],
  data: {
    i18nScopes: ['common', 'order', 'orderStatus', 'serviceType'],
    statusInfo: {},
    serviceLabel: '',
    priceText: '¥0.00',
    familyMemberText: ''
  },

  properties: {
    order: {
      type: Object,
      value: {}
    }
  },

  observers: {
    'order': function (val) {
      if (!val) return
      var stColor = (ORDER_STATUS[val.status] && ORDER_STATUS[val.status].color) || '#999'
      var statusLabel = val.status ? i18n.t('orderStatus.' + val.status) : i18n.t('order.statusUnknown')
      // i18n.t 未命中会返回 key 本身，降级为未知
      if (statusLabel === 'orderStatus.' + val.status) {
        statusLabel = i18n.t('order.statusUnknown')
      }
      var serviceLabel = val.service_type ? i18n.t('serviceType.' + val.service_type) : ''
      if (serviceLabel === 'serviceType.' + val.service_type) {
        serviceLabel = ''
      }
      var famText = ''
      if (val.family_member && val.family_member.name) {
        famText = val.family_member.name + '（' + relationLabel(val.family_member.relation) + '）'
      }
      this.setData({
        statusInfo: { label: statusLabel, color: stColor },
        serviceLabel: serviceLabel,
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
