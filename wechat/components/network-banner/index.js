// Global "network unstable" banner.
//
// Subscribes to utils/degradation on attach, renders a thin warning strip
// at the top of any page that includes <network-banner />. Auto-hides when
// degraded state clears.
const degradation = require('../../utils/degradation')
const i18nBehavior = require('../../behaviors/i18n')

Component({
  behaviors: [i18nBehavior],
  data: {
    i18nScopes: ['networkBanner'],
    visible: false,
    reason: '',
  },
  lifetimes: {
    attached: function () {
      const self = this
      this._unsub = degradation.subscribe(function (degraded) {
        self.setData({
          visible: !!degraded,
          reason: degradation.getDegradedReason() || '',
        })
      })
      // initial sync
      this.setData({
        visible: degradation.isDegraded(),
        reason: degradation.getDegradedReason() || '',
      })
    },
    detached: function () {
      if (this._unsub) this._unsub()
    },
  },
  methods: {
    onTapRetry: function () {
      degradation.clearDegraded()
      this.triggerEvent('retry')
    },
  },
})
