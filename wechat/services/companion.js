const { request } = require('./api')

function getCompanions(params = {}) {
  let url = 'companions'
  const queryParts = []
  if (params.page) queryParts.push('page=' + params.page)
  if (params.area) queryParts.push('area=' + params.area)
  if (queryParts.length > 0) url += '?' + queryParts.join('&')
  return request({ url, method: 'GET' })
}

function getCompanionDetail(companionId) {
  return request({ url: 'companions/' + companionId, method: 'GET' })
}

function getCompanionReviews(companionId) {
  return request({ url: 'companions/' + companionId + '/reviews', method: 'GET' })
}

module.exports = { getCompanions, getCompanionDetail, getCompanionReviews }
