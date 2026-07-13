const router = require('../../../utils/router')
const { getOrders } = require('../../../services/order')
const i18n = require('../../../utils/i18n')
const i18nBehavior = require('../../../behaviors/i18n')

Page({
  behaviors: [i18nBehavior],
  data: {
    i18nScopes: ['chat'],
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
    // R-07: 三个独立请求并发，首屏延迟从 3x 降到 1x
    Promise.all([
      getOrders({ status: 'accepted' }),
      getOrders({ status: 'in_progress' }),
      getOrders({ status: 'completed' }),
    ])
      .then(results => {
        const [acceptedRes, inProgressRes, completedRes] = results
        const accepted = (acceptedRes.items || []).map(this._orderToConversation)
        const inProgress = (inProgressRes.items || []).map(this._orderToConversation)
        const completed = (completedRes.items || []).map(this._orderToConversation)
        this.setData({
          conversations: accepted.concat(inProgress).concat(completed),
          loading: false,
        })
      })
      .catch(() => {
        this.setData({ loading: false })
      })
  },

  _orderToConversation(order) {
    // Companion sees patient name + hospital
    var name = i18n.t('chat.defaultName')
    if (order.patient_name) {
      name = i18n.t('chat.patientPrefix', { name: order.patient_name })
    }
    if (order.hospital_name) {
      name = name + ' - ' + order.hospital_name
    }
    return {
      id: order.id,
      name: name,
      lastMessage: order.status === 'completed' ? i18n.t('chat.hintCompleted') : i18n.t('chat.tapToEnter'),
      lastTime: order.appointment_date || '',
      unreadCount: 0,
    }
  },

  onConversationTap(e) {
    const id = e.currentTarget.dataset.id
    const name = e.currentTarget.dataset.name
    router.navigate({
      url: '/pages/chat/room/index?id=' + id + '&name=' + encodeURIComponent(name)
    })
  }
})
