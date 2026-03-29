const { request } = require('./api')

function getMe() {
  return request({ url: 'users/me', method: 'GET' })
}

function updateMe(data) {
  return request({ url: 'users/me', method: 'PUT', data })
}

module.exports = { getMe, updateMe }
