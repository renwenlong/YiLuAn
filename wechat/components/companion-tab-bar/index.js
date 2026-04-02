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
        home: '/pages/companion/home/index',
        orders: '/pages/companion/orders/index',
        chat: '/pages/companion/chat/index',
        profile: '/pages/companion/profile/index'
      }
      var url = routes[page]
      if (!url) return
      wx.reLaunch({ url: url })
    }
  }
})
