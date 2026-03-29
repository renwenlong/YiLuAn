const { request } = require('./api')

function getHospitals(params = {}) {
  let url = 'hospitals'
  const queryParts = []
  if (params.keyword) queryParts.push('keyword=' + encodeURIComponent(params.keyword))
  if (queryParts.length > 0) url += '?' + queryParts.join('&')
  return request({ url, method: 'GET' })
}

module.exports = { getHospitals, searchHospitals: getHospitals }
