const { request } = require('./api')
const { setAccessToken, setRefreshToken, getRefreshToken, clearTokens } = require('../utils/token')
const store = require('../store/index')

function _getAppSafely() {
  // 测试环境下 getApp 可能不存在或未初始化
  if (typeof getApp !== 'function') return null
  try {
    return getApp()
  } catch (e) {
    return null
  }
}

function _afterLogin(user) {
  const app = _getAppSafely()
  if (app && typeof app.connectNotificationWs === 'function') {
    app.connectNotificationWs()
  }
  return user
}

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
          _afterLogin(data.user)
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

function verifyOTP(phone, code) {
  return request({
    url: 'auth/verify-otp',
    method: 'POST',
    data: { phone, code },
    auth: false,
  }).then(data => {
    setAccessToken(data.access_token)
    setRefreshToken(data.refresh_token)
    store.setState({ isAuthenticated: true, user: data.user })
    _afterLogin(data.user)
    return data.user
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
  const app = _getAppSafely()
  if (app && typeof app.disconnectNotificationWs === 'function') {
    app.disconnectNotificationWs()
  }
  clearTokens()
  store.reset()
  wx.reLaunch({ url: '/pages/login/index' })
}

module.exports = { wechatLogin, refreshToken, sendOTP, verifyOTP, bindPhone, logout }
