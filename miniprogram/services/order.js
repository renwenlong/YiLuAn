const { request } = require('./api')
const config = require('../config/index')

function getOrders(params = {}) {
  const { status, page = 1 } = params
  let url = 'orders'
  const queryParts = []
  if (status) queryParts.push('status=' + status)
  queryParts.push('page=' + page)
  queryParts.push('page_size=' + config.PAGE_SIZE)
  if (queryParts.length > 0) url += '?' + queryParts.join('&')
  return request({ url, method: 'GET' })
}

function createOrder(data) {
  return request({ url: 'orders', method: 'POST', data })
}

function getOrderDetail(orderId) {
  return request({ url: 'orders/' + orderId, method: 'GET' })
}

function orderAction(orderId, action) {
  return request({ url: 'orders/' + orderId + '/' + action, method: 'POST' })
}

module.exports = { getOrders, createOrder, getOrderDetail, orderAction }
