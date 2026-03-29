const config = require('../config/index')
const { getAccessToken, setAccessToken, setRefreshToken, getRefreshToken, clearTokens } = require('../utils/token')

let _isRefreshing = false
let _refreshQueue = []

function request({ url, method = 'GET', data, auth = true }) {
  return new Promise((resolve, reject) => {
    const header = { 'Content-Type': 'application/json' }
    if (auth) {
      const token = getAccessToken()
      if (token) {
        header['Authorization'] = 'Bearer ' + token
      }
    }

    wx.request({
      url: config.API_BASE_URL + '/' + url,
      method,
      data,
      header,
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data)
        } else if (res.statusCode === 401 && auth) {
          _handleUnauthorized({ url, method, data, auth }, resolve, reject)
        } else {
          reject({ statusCode: res.statusCode, data: res.data })
        }
      },
      fail(err) {
        reject({ statusCode: 0, data: err })
      },
    })
  })
}

function _handleUnauthorized(originalRequest, resolve, reject) {
  if (_isRefreshing) {
    _refreshQueue.push({ originalRequest, resolve, reject })
    return
  }

  _isRefreshing = true
  const refreshToken = getRefreshToken()
  if (!refreshToken) {
    _isRefreshing = false
    _forceLogout()
    reject({ statusCode: 401, data: { detail: 'No refresh token' } })
    return
  }

  wx.request({
    url: config.API_BASE_URL + '/auth/refresh',
    method: 'POST',
    data: { refresh_token: refreshToken },
    header: { 'Content-Type': 'application/json' },
    success(res) {
      if (res.statusCode === 200 && res.data.access_token) {
        setAccessToken(res.data.access_token)
        setRefreshToken(res.data.refresh_token)
        _isRefreshing = false

        // Retry original request
        request(originalRequest).then(resolve).catch(reject)

        // Retry queued requests
        _refreshQueue.forEach(item => {
          request(item.originalRequest).then(item.resolve).catch(item.reject)
        })
        _refreshQueue = []
      } else {
        _isRefreshing = false
        _refreshQueue = []
        _forceLogout()
        reject({ statusCode: 401, data: res.data })
      }
    },
    fail() {
      _isRefreshing = false
      _refreshQueue = []
      _forceLogout()
      reject({ statusCode: 0, data: { detail: 'Network error during refresh' } })
    },
  })
}

function _forceLogout() {
  clearTokens()
  const store = require('../store/index')
  store.reset()
  wx.reLaunch({ url: '/pages/login/index' })
}

module.exports = { request }
