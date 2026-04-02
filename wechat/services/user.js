const { request } = require('./api')
const config = require('../config/index')
const { getAccessToken } = require('../utils/token')

function getMe() {
  return request({ url: 'users/me', method: 'GET' })
}

function updateMe(data) {
  return request({ url: 'users/me', method: 'PUT', data })
}

function getPatientProfile() {
  return request({ url: 'users/me/patient-profile', method: 'GET' })
}

function updatePatientProfile(data) {
  return request({ url: 'users/me/patient-profile', method: 'PUT', data })
}

function uploadAvatar(filePath) {
  return new Promise((resolve, reject) => {
    const token = getAccessToken()
    wx.uploadFile({
      url: config.API_BASE_URL + '/users/me/avatar',
      filePath: filePath,
      name: 'file',
      header: {
        'Authorization': 'Bearer ' + (token || '')
      },
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          var data = res.data
          if (typeof data === 'string') {
            try { data = JSON.parse(data) } catch (e) { /* use as-is */ }
          }
          resolve(data)
        } else {
          reject({ statusCode: res.statusCode, data: res.data })
        }
      },
      fail(err) {
        reject({ statusCode: 0, data: err })
      }
    })
  })
}

function switchRole(role) {
  return request({ url: 'users/me/switch-role', method: 'POST', data: { role } })
}

module.exports = { getMe, updateMe, getPatientProfile, updatePatientProfile, uploadAvatar, switchRole }
