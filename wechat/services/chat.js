const { request } = require('./api')

function getChatMessages(orderId, params = {}) {
  let url = 'chats/' + orderId + '/messages'
  if (params.before) url += '?before=' + params.before
  return request({ url, method: 'GET' })
}

function sendMessage(orderId, data) {
  return request({
    url: 'chats/' + orderId + '/messages',
    method: 'POST',
    data: data,
  })
}

function markRead(orderId) {
  return request({
    url: 'chats/' + orderId + '/read',
    method: 'POST',
  })
}

module.exports = { getChatMessages, sendMessage, markRead }
