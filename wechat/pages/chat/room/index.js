const { getChatMessages } = require('../../../services/chat')
const { getOrderDetail, orderAction } = require('../../../services/order')
const ws = require('../../../services/websocket')
const store = require('../../../store/index')

Page({
  data: {
    messages: [],
    inputValue: '',
    orderId: '',
    scrollIntoView: '',
    currentUserId: '',
    orderStatus: ''
  },

  onLoad(options) {
    const user = store.getState().user || {}
    this.setData({
      orderId: options.id,
      currentUserId: user.id || ''
    })
    this.loadHistory()
    this.loadOrderStatus()
    this.connectWebSocket()
  },

  onUnload() {
    ws.disconnect()
  },

  async loadOrderStatus() {
    try {
      const order = await getOrderDetail(this.data.orderId)
      this.setData({ orderStatus: order.status || '' })
    } catch (err) {}
  },

  async loadHistory() {
    try {
      const res = await getChatMessages(this.data.orderId)
      const messages = res.items || []
      this.setData({ messages })
      this.scrollToBottom()
    } catch (err) {
      wx.showToast({ title: '加载消息失败', icon: 'none' })
    }
  },

  connectWebSocket() {
    ws.connect({
      orderId: this.data.orderId,
      onMessage: (msg) => {
        if (msg.sender_id === this.data.currentUserId) return
        this.setData({
          messages: [...this.data.messages, msg]
        })
        this.scrollToBottom()
      },
      onError: () => {
        wx.showToast({ title: '连接断开，正在重连...', icon: 'none', duration: 2000 })
      }
    })
  },

  onInput(e) {
    this.setData({ inputValue: e.detail.value })
  },

  onSend() {
    const { inputValue, orderId, currentUserId } = this.data
    const content = inputValue.trim()
    if (!content) return

    ws.send({ content, type: 'text' })

    const message = {
      id: Date.now().toString(),
      order_id: orderId,
      sender_id: currentUserId,
      content,
      created_at: new Date().toISOString(),
      type: 'text'
    }

    this.setData({
      messages: [...this.data.messages, message],
      inputValue: ''
    })
    this.scrollToBottom()
  },

  onViewOrder() {
    wx.navigateTo({
      url: '/pages/patient/order-detail/index?id=' + this.data.orderId
    })
  },

  onAcceptOrder() {
    var self = this
    wx.showModal({
      title: '确认接单',
      content: '确定接受此订单吗？',
      success: function (res) {
        if (!res.confirm) return
        orderAction(self.data.orderId, 'accept').then(function () {
          wx.showToast({ title: '已接单', icon: 'success' })
          self.setData({ orderStatus: 'accepted' })
        }).catch(function () {
          wx.showToast({ title: '接单失败', icon: 'none' })
        })
      }
    })
  },

  scrollToBottom() {
    const { messages } = this.data
    if (messages.length > 0) {
      this.setData({
        scrollIntoView: `msg-${messages.length - 1}`
      })
    }
  }
})
