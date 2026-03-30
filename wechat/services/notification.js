const { request } = require('./api')

function getNotifications(params = {}) {
  const { page = 1, page_size = 20 } = params
  return request({
    url: 'notifications?page=' + page + '&page_size=' + page_size,
    method: 'GET',
  })
}

function getUnreadCount() {
  return request({
    url: 'notifications/unread-count',
    method: 'GET',
  })
}

function markRead(notificationId) {
  return request({
    url: 'notifications/' + notificationId + '/read',
    method: 'POST',
  })
}

function markAllRead() {
  return request({
    url: 'notifications/read-all',
    method: 'POST',
  })
}

module.exports = { getNotifications, getUnreadCount, markRead, markAllRead }
