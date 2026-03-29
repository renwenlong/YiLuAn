const { getChatMessages } = require('../../../services/chat')
const ws = require('../../../services/websocket')
const store = require('../../../store/index')

Page({
  data: {
    messages: [],
    inputValue: '',
    orderId: '',
    scrollIntoView: '',
    currentUserId: ''
  },

  onLoad(options) {
    const userInfo = store.getState().userInfo || {}
    this.setData({
      orderId: options.id,
      currentUserId: userInfo.id || ''
    })
    this.loadHistory()
    this.connectWebSocket()
  },

  onUnload() {
    ws.disconnect()
  },

  async loadHistory() {
    try {
      const messages = await getChatMessages(this.data.orderId)
      this.setData({ messages: messages || [] })
      this.scrollToBottom()
    } catch (err) {
      wx.showToast({ title: '加载消息失败', icon: 'none' })
    }
  },

  connectWebSocket() {
    ws.connect({
      orderId: this.data.orderId,
      onMessage: (msg) => {
        this.setData({
          messages: [...this.data.messages, msg]
        })
        this.scrollToBottom()
      },
      onError: () => {
        wx.showToast({ title: '连接断开，正在重连...', icon: 'none' })
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

    const message = {
      id: Date.now().toString(),
      orderId,
      senderId: currentUserId,
      content,
      timestamp: new Date().toISOString(),
      type: 'text'
    }

    ws.send(message)

    this.setData({
      messages: [...this.data.messages, message],
      inputValue: ''
    })
    this.scrollToBottom()
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
