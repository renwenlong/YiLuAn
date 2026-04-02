Component({
  properties: {
    active: {
      type: String,
      value: 'home'
    }
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
      wx.reLaunch({ url: url })
    }
  }
})
