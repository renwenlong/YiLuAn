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
    const user = store.getState().user || {}
    this.setData({
      orderId: options.id,
      currentUserId: user.id || ''
    })
    this.loadHistory()
    this.connectWebSocket()
  },

  onUnload() {
    ws.disconnect()
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
        // Skip own messages (already added optimistically in onSend)
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

    // Send to WebSocket — backend only needs content and type
    ws.send({ content, type: 'text' })

    // Optimistic local display using snake_case to match backend/chat-bubble
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

  scrollToBottom() {
    const { messages } = this.data
    if (messages.length > 0) {
      this.setData({
        scrollIntoView: `msg-${messages.length - 1}`
      })
    }
  }
})
