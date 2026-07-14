const router = require('../../utils/router')
const i18nBehavior = require('../../behaviors/i18n')
Component({
  behaviors: [i18nBehavior],
  properties: {
    active: {
      type: String,
      value: 'home'
    }
  },

  data: {
    i18nScopes: ['tabBar']
  },

  methods: {
    onTap(e) {
      var page = e.currentTarget.dataset.page
      if (page === this.data.active) return

      var routes = {
        home: '/pages/patient/home/index',
        orders: '/pages/orders/index',
        chat: '/pages/chat/list/index',
        profile: '/pages/profile/index'
      }
      var url = routes[page]
      if (!url) return
      router.relaunch({ url: url })
    }
  }
})
