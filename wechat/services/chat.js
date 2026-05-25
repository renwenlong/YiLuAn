const { request } = require('./api')

/**
 * Fetch chat messages for an order.
 *
 * Two modes:
 * - Default page mode: `getChatMessages(orderId)` → page=1, page_size=50.
 * - Cursor mode (pull-up history): `getChatMessages(orderId, { beforeId, limit })`
 *   returns up to `limit` messages strictly older than `beforeId`, in
 *   ascending order, plus `has_more` / `next_before_id` for the next page.
 *
 * Legacy alias `params.before` is still accepted for back-compat with
 * older callers and existing tests.
 */
function getChatMessages(orderId, params = {}) {
  const qs = []
  const beforeId = params.beforeId || params.before_id || params.before
  if (beforeId) qs.push('before_id=' + encodeURIComponent(beforeId))
  if (params.limit) qs.push('limit=' + encodeURIComponent(params.limit))
  if (params.page) qs.push('page=' + encodeURIComponent(params.page))
  if (params.page_size) qs.push('page_size=' + encodeURIComponent(params.page_size))

  let url = 'chats/' + orderId + '/messages'
  if (qs.length) url += '?' + qs.join('&')
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
