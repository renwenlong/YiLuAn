const { request } = require('./api')

function getCompanions(params = {}) {
  let url = 'companions'
  const queryParts = []
  if (params.page) queryParts.push('page=' + params.page)
  if (params.page_size) queryParts.push('page_size=' + params.page_size)
  if (params.area) queryParts.push('area=' + params.area)
  if (params.service_type) queryParts.push('service_type=' + params.service_type)
  if (queryParts.length > 0) url += '?' + queryParts.join('&')
  return request({ url, method: 'GET' })
}

function getCompanionDetail(companionId) {
  return request({ url: 'companions/' + companionId, method: 'GET' })
}

function getCompanionReviews(companionId) {
  return request({ url: 'companions/' + companionId + '/reviews', method: 'GET' })
}

function applyCompanion(data) {
  return request({ url: 'companions/apply', method: 'POST', data })
}

function updateCompanionProfile(data) {
  return request({ url: 'companions/me', method: 'PUT', data })
}

function getCompanionStats() {
  return request({ url: 'companions/me/stats', method: 'GET' })
}

module.exports = { getCompanions, getCompanionDetail, getCompanionReviews, applyCompanion, updateCompanionProfile, getCompanionStats }
