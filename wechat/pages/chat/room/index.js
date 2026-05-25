const { getChatMessages, markRead } = require('../../../services/chat')
const { getOrderDetail, orderAction } = require('../../../services/order')
const ws = require('./services/websocket')
const store = require('../../../store/index')
const router = require('../../../utils/router')

const HISTORY_PAGE_SIZE = 30

Page({
  data: {
    messages: [],
    inputValue: '',
    orderId: '',
    scrollIntoView: '',
    currentUserId: '',
    orderStatus: '',
    // Pull-up history pagination state
    hasMoreHistory: false,
    loadingMore: false,
    historyExhausted: false,
    // null = first load (no anchor); set to oldest message id we have locally
    oldestId: null
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
    this.markMessagesRead()
  },

  onUnload() {
    ws.disconnect()
  },

  async markMessagesRead() {
    // 打开聊天页时，自动将本订单的未读消息标为已读，
    // 保证未读角标和列表红点及时清零。失败不阻断主流程。
    try {
      await markRead(this.data.orderId)
    } catch (err) {}
  },

  async loadOrderStatus() {
    try {
      const order = await getOrderDetail(this.data.orderId)
      this.setData({ orderStatus: order.status || '' })
    } catch (err) {}
  },

  async loadHistory() {
    try {
      const res = await getChatMessages(this.data.orderId, {
        limit: HISTORY_PAGE_SIZE
      })
      const messages = res.items || []
      const oldestId = messages.length > 0 ? messages[0].id : null
      // On first load we always allow one upward fetch attempt; the server
      // tells us via has_more whether more pages exist.
      this.setData({
        messages,
        oldestId,
        hasMoreHistory: !!res.has_more,
        historyExhausted: !res.has_more && messages.length < HISTORY_PAGE_SIZE
      })
      this.scrollToBottom()
    } catch (err) {
      wx.showToast({ title: '加载消息失败', icon: 'none' })
    }
  },

  /**
   * scroll-view bindscrolltoupper handler — user pulled the list to the top,
   * load the previous page of history and prepend it.
   */
  async onScrollToUpper() {
    const { loadingMore, historyExhausted, oldestId, orderId } = this.data
    if (loadingMore || historyExhausted || !oldestId) return

    this.setData({ loadingMore: true })
    try {
      const res = await getChatMessages(orderId, {
        beforeId: oldestId,
        limit: HISTORY_PAGE_SIZE
      })
      const older = res.items || []
      if (older.length === 0) {
        this.setData({
          loadingMore: false,
          historyExhausted: true,
          hasMoreHistory: false
        })
        return
      }
      const newOldest = older[0].id
      const merged = older.concat(this.data.messages)
      // Anchor scroll position on the first previously-visible message so the
      // viewport doesn't jump to the new top. `older.length` is the index of
      // what used to be `messages[0]` in the new list.
      this.setData({
        messages: merged,
        oldestId: newOldest,
        hasMoreHistory: !!res.has_more,
        historyExhausted: !res.has_more,
        loadingMore: false,
        scrollIntoView: `msg-${older.length}`
      })
    } catch (err) {
      this.setData({ loadingMore: false })
      wx.showToast({ title: '加载历史失败', icon: 'none' })
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
    router.navigate({
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
