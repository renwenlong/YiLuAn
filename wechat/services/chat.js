const { request } = require('./api')

function getChatMessages(orderId, params = {}) {
  let url = 'chats/' + orderId + '/messages'
  if (params.before) url += '?before=' + params.before
  return request({ url, method: 'GET' })
}

module.exports = { getChatMessages }
