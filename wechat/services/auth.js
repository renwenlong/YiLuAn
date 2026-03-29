const { request } = require('./api')
const { setAccessToken, setRefreshToken, getRefreshToken, clearTokens } = require('../utils/token')
const store = require('../store/index')

function wechatLogin() {
  return new Promise((resolve, reject) => {
    wx.login({
      success(loginRes) {
        if (!loginRes.code) {
          reject(new Error('wx.login failed'))
          return
        }
        request({
          url: 'auth/wechat-login',
          method: 'POST',
          data: { code: loginRes.code },
          auth: false,
        }).then(data => {
          setAccessToken(data.access_token)
          setRefreshToken(data.refresh_token)
          store.setState({ isAuthenticated: true, user: data.user })
          resolve(data.user)
        }).catch(reject)
      },
      fail(err) {
        reject(err)
      },
    })
  })
}

function refreshToken() {
  const token = getRefreshToken()
  return request({
    url: 'auth/refresh',
    method: 'POST',
    data: { refresh_token: token },
    auth: false,
  }).then(data => {
    setAccessToken(data.access_token)
    setRefreshToken(data.refresh_token)
    return data
  })
}

function sendOTP(phone) {
  return request({
    url: 'auth/send-otp',
    method: 'POST',
    data: { phone },
    auth: false,
  })
}

function bindPhone(phone, code) {
  return request({
    url: 'auth/bind-phone',
    method: 'POST',
    data: { phone, code },
    auth: true,
  })
}

function logout() {
  clearTokens()
  store.reset()
  wx.reLaunch({ url: '/pages/login/index' })
}

module.exports = { wechatLogin, refreshToken, sendOTP, bindPhone, logout }
