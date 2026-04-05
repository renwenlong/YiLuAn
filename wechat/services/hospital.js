const { request } = require('./api')

function getHospitals(params = {}) {
  let url = 'hospitals'
  const queryParts = []
  if (params.keyword) queryParts.push('keyword=' + encodeURIComponent(params.keyword))
  if (params.province) queryParts.push('province=' + encodeURIComponent(params.province))
  if (params.city) queryParts.push('city=' + encodeURIComponent(params.city))
  if (params.district) queryParts.push('district=' + encodeURIComponent(params.district))
  if (params.level) queryParts.push('level=' + encodeURIComponent(params.level))
  if (params.tag) queryParts.push('tag=' + encodeURIComponent(params.tag))
  if (params.page) queryParts.push('page=' + params.page)
  if (params.page_size) queryParts.push('page_size=' + params.page_size)
  if (queryParts.length > 0) url += '?' + queryParts.join('&')
  return request({ url, method: 'GET' })
}

function getHospitalFilters(params = {}) {
  let url = 'hospitals/filters'
  const queryParts = []
  if (params.province) queryParts.push('province=' + encodeURIComponent(params.province))
  if (params.city) queryParts.push('city=' + encodeURIComponent(params.city))
  if (queryParts.length > 0) url += '?' + queryParts.join('&')
  return request({ url, method: 'GET' })
}

function getHospitalDetail(id) {
  return request({ url: 'hospitals/' + id, method: 'GET' })
}

function getNearestRegion(latitude, longitude) {
  return request({
    url: 'hospitals/nearest-region?latitude=' + latitude + '&longitude=' + longitude,
    method: 'GET'
  })
}

module.exports = { getHospitals, searchHospitals: getHospitals, getHospitalFilters, getHospitalDetail, getNearestRegion }
