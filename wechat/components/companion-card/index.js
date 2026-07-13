const i18nBehavior = require('../../behaviors/i18n')
const i18n = require('../../utils/i18n')

Component({
  behaviors: [i18nBehavior],
  properties: {
    companion: {
      type: Object,
      value: {},
      observer: function (val) {
        var count = (val && val.completed_orders) || 0
        this.setData({ completedText: i18n.t('companionCard.completedCount', { count: count }) })
      }
    },
    showBook: {
      type: Boolean,
      value: false
    }
  },

  data: {
    i18nScopes: ['companionCard'],
    completedText: ''
  },

  methods: {
    onTap: function () {
      this.triggerEvent('tap', { id: this.data.companion.id })
    },
    onBook: function () {
      this.triggerEvent('book', { id: this.data.companion.id })
    }
  }
})
