const config = require('../config/index')
const { getAccessToken, setAccessToken, setRefreshToken, getRefreshToken, clearTokens } = require('../utils/token')

let _isRefreshing = false
let _refreshQueue = []

function request({ url, method = 'GET', data, auth = true, _skipPhoneRequiredHandler = false }) {
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
        } else if (
          res.statusCode === 400
          && !_skipPhoneRequiredHandler
          && _extractErrorCode(res.data) === 'PHONE_REQUIRED'
        ) {
          _handlePhoneRequired(res.data, reject)
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

// 提取后端返回体里的机器可读错误码（detail 可能是 string 或 {error_code, message}）
function _extractErrorCode(payload) {
  if (!payload) return null
  const detail = payload.detail
  if (detail && typeof detail === 'object' && detail.error_code) {
    return detail.error_code
  }
  return null
}

// 遇到 PHONE_REQUIRED 统一弹窗 + 跳转绑定页，原调用者以 reject 结束（上层不必重复处理）
function _handlePhoneRequired(payload, reject) {
  const detail = payload && payload.detail
  const message = (detail && detail.message) || '请先绑定手机号'
  // 拿当前页路径，跳转绑定后可回跳
  let redirect = ''
  try {
    const pages = getCurrentPages()
    if (pages && pages.length) {
      const cur = pages[pages.length - 1]
      const opts = cur.options || {}
      const qs = Object.keys(opts).map(k => `${k}=${encodeURIComponent(opts[k])}`).join('&')
      redirect = '/' + cur.route + (qs ? '?' + qs : '')
    }
  } catch (e) {
    // 忽略
  }

  wx.showModal({
    title: '请先绑定手机号',
    content: message,
    confirmText: '去绑定',
    cancelText: '取消',
    success(res) {
      if (res.confirm) {
        const url = '/pages/profile/bind-phone/index'
          + (redirect ? '?redirect=' + encodeURIComponent(redirect) : '')
        wx.navigateTo({ url })
      }
    }
  })
  reject({ statusCode: 400, data: payload, handled: true })
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
