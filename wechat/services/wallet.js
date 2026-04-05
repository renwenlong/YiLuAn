const { request } = require('./api')

function getWalletSummary() {
  return request({ url: 'wallet', method: 'GET' })
}

function getTransactions(params) {
  params = params || {}
  var url = 'wallet/transactions'
  var parts = []
  if (params.page) parts.push('page=' + params.page)
  if (params.page_size) parts.push('page_size=' + params.page_size)
  if (parts.length > 0) url += '?' + parts.join('&')
  return request({ url: url, method: 'GET' })
}

module.exports = { getWalletSummary, getTransactions }
