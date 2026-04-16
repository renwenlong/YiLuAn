const store = require('../../../store/index')
const { getOrders } = require('../../../services/order')
const { getChatMessages } = require('../../../services/chat')

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
    var self = this
    var statuses = ['created', 'accepted', 'in_progress', 'completed']

    var promises = statuses.map(function (status) {
      return getOrders({ status: status }).then(function (res) {
        return res.items || []
      }).catch(function () { return [] })
    })

    Promise.all(promises).then(function (results) {
      var allOrders = []
      results.forEach(function (items) {
        allOrders = allOrders.concat(items)
      })
      var conversations = allOrders.map(function (order) {
        return self._orderToConversation(order)
      })
      self.setData({ conversations: conversations, loading: false })
      self._fetchUnreadCounts(conversations)
    }).catch(function () {
      self.setData({ loading: false })
    })
  },

  _fetchUnreadCounts(conversations) {
    var self = this
    var user = store.getState().user || {}
    var userId = user.id || ''

    conversations.forEach(function (conv, idx) {
      getChatMessages(conv.id).then(function (res) {
        var messages = res.items || []
        if (messages.length === 0) return
        var lastMsg = messages[messages.length - 1]
        var unread = 0
        for (var i = messages.length - 1; i >= 0; i--) {
          if (messages[i].sender_id !== userId && !messages[i].is_read) {
            unread++
          }
        }
        var update = {}
        update['conversations[' + idx + '].unreadCount'] = unread
        update['conversations[' + idx + '].lastMessage'] = lastMsg.type === 'system' ? '[系统] ' + lastMsg.content : lastMsg.content
        update['conversations[' + idx + '].lastTime'] = (lastMsg.created_at || '').substring(0, 16).replace('T', ' ')
        self.setData(update)
      }).catch(function () {})
    })
  },

  _orderToConversation(order) {
    var name = '聊天'
    if (order.companion_name) {
      name = '陪诊师·' + order.companion_name
    }
    if (order.hospital_name) {
      name = name + ' - ' + order.hospital_name
    }
    var statusHints = {
      created: '待接单',
      completed: '订单已完成',
      reviewed: '已评价'
    }
    return {
      id: order.id,
      name: name,
      status: order.status,
      lastMessage: statusHints[order.status] || '点击进入聊天',
      lastTime: order.appointment_date || '',
      unreadCount: 0,
    }
  },

  onConversationTap(e) {
    var id = e.currentTarget.dataset.id
    var name = e.currentTarget.dataset.name
    wx.navigateTo({
      url: '/pages/chat/room/index?id=' + id + '&name=' + encodeURIComponent(name)
    })
  }
})
