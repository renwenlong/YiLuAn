const store = require('../../../store/index')

Page({
  data: {
    conversations: []
  },

  onLoad() {
    this.fetchConversations()
  },

  onShow() {
    this.fetchConversations()
  },

  fetchConversations() {
    // TODO: replace with actual chat API
    // Placeholder data for development
    this.setData({
      conversations: []
    })
  },

  onConversationTap(e) {
    const id = e.currentTarget.dataset.id
    const name = e.currentTarget.dataset.name
    wx.navigateTo({
      url: '/pages/chat/room/index?id=' + id + '&name=' + encodeURIComponent(name)
    })
  }
})
