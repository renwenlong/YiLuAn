const store = require('../../../store/index')
const router = require('../../../utils/router')
const { getOrders } = require('../../../services/order')
const { getChatMessages } = require('../../../services/chat')
const i18n = require('../../../utils/i18n')
const i18nBehavior = require('../../../behaviors/i18n')

Page({
  behaviors: [i18nBehavior],
  data: {
    i18nScopes: ['common', 'chat'],
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
        update['conversations[' + idx + '].lastMessage'] = lastMsg.type === 'system' ? i18n.t('chat.systemPrefix') + lastMsg.content : lastMsg.content
        update['conversations[' + idx + '].lastTime'] = (lastMsg.created_at || '').substring(0, 16).replace('T', ' ')
        self.setData(update)
      }).catch(function () {})
    })
  },

  _orderToConversation(order) {
    var name = i18n.t('chat.defaultName')
    if (order.companion_name) {
      name = i18n.t('chat.companionPrefix', { name: order.companion_name })
    }
    if (order.hospital_name) {
      name = name + ' - ' + order.hospital_name
    }
    var statusHints = {
      created: i18n.t('chat.hintCreated'),
      completed: i18n.t('chat.hintCompleted'),
      reviewed: i18n.t('chat.hintReviewed')
    }
    return {
      id: order.id,
      name: name,
      status: order.status,
      lastMessage: statusHints[order.status] || i18n.t('chat.tapToEnter'),
      lastTime: order.appointment_date || '',
      unreadCount: 0,
    }
  },

  onConversationTap(e) {
    var id = e.currentTarget.dataset.id
    var name = e.currentTarget.dataset.name
    router.navigate({
      url: '/pages/chat/room/index?id=' + id + '&name=' + encodeURIComponent(name)
    })
  }
})
