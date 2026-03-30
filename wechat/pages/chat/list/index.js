const store = require('../../../store/index')
const { getOrders } = require('../../../services/order')

Page({
  data: {
    conversations: [],
    loading: false
  },

  onLoad() {
    this.fetchConversations()
  },

  onShow() {
    this.fetchConversations()
  },

  fetchConversations() {
    this.setData({ loading: true })
    // Fetch orders with chat-eligible statuses
    getOrders({ status: 'accepted' })
      .then(res => {
        const accepted = (res.items || []).map(this._orderToConversation)
        return getOrders({ status: 'in_progress' }).then(res2 => {
          const inProgress = (res2.items || []).map(this._orderToConversation)
          return getOrders({ status: 'completed' }).then(res3 => {
            const completed = (res3.items || []).map(this._orderToConversation)
            this.setData({
              conversations: accepted.concat(inProgress).concat(completed),
              loading: false,
            })
          })
        })
      })
      .catch(() => {
        this.setData({ loading: false })
      })
  },

  _orderToConversation(order) {
    return {
      id: order.id,
      name: order.companion_name || order.patient_name || '聊天',
      lastMessage: order.status === 'completed' ? '订单已完成' : '点击进入聊天',
      lastTime: order.appointment_date || '',
      unreadCount: 0,
    }
  },

  onConversationTap(e) {
    const id = e.currentTarget.dataset.id
    const name = e.currentTarget.dataset.name
    wx.navigateTo({
      url: '/pages/chat/room/index?id=' + id + '&name=' + encodeURIComponent(name)
    })
  }
})
