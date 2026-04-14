const { request } = require('./api')
const config = require('../config/index')

function getOrders(params = {}) {
  const { status, city, page = 1, page_size } = params
  let url = 'orders'
  const queryParts = []
  if (status) queryParts.push('status=' + status)
  if (city) queryParts.push('city=' + encodeURIComponent(city))
  queryParts.push('page=' + page)
  queryParts.push('page_size=' + (page_size || config.PAGE_SIZE))
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

function payOrder(orderId) {
  return request({ url: 'orders/' + orderId + '/pay', method: 'POST' })
}

/**
 * Call wx.requestPayment with sign_params from backend.
 * For mock provider, resolves immediately without calling wx.requestPayment.
 * Returns: { success: true } or throws on failure/cancel.
 */
function requestWechatPayment(payResult) {
  // Mock provider: skip wx.requestPayment, treat as instant success
  if (payResult.provider === 'mock' || payResult.mock_success) {
    return Promise.resolve({ success: true, mock: true })
  }

  var params = payResult.sign_params
  if (!params) {
    return Promise.reject({ errMsg: 'Missing sign_params from server' })
  }

  return new Promise(function (resolve, reject) {
    wx.requestPayment({
      timeStamp: params.timeStamp,
      nonceStr: params.nonceStr,
      package: params.package,
      signType: params.signType || 'RSA',
      paySign: params.paySign,
      success: function (res) {
        resolve({ success: true, result: res })
      },
      fail: function (err) {
        if (err.errMsg && err.errMsg.indexOf('cancel') !== -1) {
          reject({ cancelled: true, errMsg: err.errMsg })
        } else {
          reject({ cancelled: false, errMsg: err.errMsg || '支付失败' })
        }
      }
    })
  })
}

function refundOrder(orderId) {
  return request({ url: 'orders/' + orderId + '/refund', method: 'POST' })
}

module.exports = { getOrders, createOrder, getOrderDetail, orderAction, payOrder, requestWechatPayment, refundOrder }
