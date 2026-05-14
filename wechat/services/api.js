const config = require('../config/index')
const { getAccessToken, setAccessToken, setRefreshToken, getRefreshToken, clearTokens } = require('../utils/token')
const { sanitizeText } = require('../utils/sanitizeText')

// Default request timeout (ms). wx.request defaults to 60s, which on flaky
// 4G / hospital wifi looks like the app froze. 15s is responsive enough
// while surviving normal latency spikes; per-call overrides via opts.timeout.
const DEFAULT_REQUEST_TIMEOUT_MS = 15000

// Generate a short, URL-safe trace id for X-Request-Id propagation. Backend
// echoes / logs it so a user complaint can be correlated with a server log
// line in seconds. Format: <millis36>-<rand6> (<= 16 chars).
function _generateRequestId() {
  const rand = Math.random().toString(36).slice(2, 8)
  return Date.now().toString(36) + '-' + rand
}

// Single in-flight refresh promise. All 401s that land while a refresh is in
// progress await this same promise instead of being queued raw, which avoids
// the old bug where a refresh-network-failure left every queued caller in
// permanent pending (forever spinner). Resolves with new access_token on
// success; rejects with the upstream error on failure.
let _refreshPromise = null

function request({ url, method = 'GET', data, auth = true, timeout, _skipGuardHandlers = false, _skipPhoneRequiredHandler = false }) {
  // `_skipPhoneRequiredHandler` 保留为向后兼容的参数。如果备调用流不希望自动触发 guard 弹窗，
  // 建议使用 `_skipGuardHandlers: true`。
  const skipGuards = _skipGuardHandlers || _skipPhoneRequiredHandler
  const requestId = _generateRequestId()
  return new Promise((resolve, reject) => {
    const header = {
      'Content-Type': 'application/json',
      'X-Request-Id': requestId,
    }
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
      timeout: timeout || DEFAULT_REQUEST_TIMEOUT_MS,
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data)
        } else if (res.statusCode === 401 && auth) {
          _handleUnauthorized({ url, method, data, auth }, resolve, reject)
        } else if (res.statusCode === 400 && !skipGuards) {
          const code = _extractErrorCode(res.data)
          if (code === 'PHONE_REQUIRED') {
            _handlePhoneRequired(res.data, reject)
          } else if (code === 'PAYMENT_REQUIRED') {
            _handlePaymentRequired(res.data, reject)
          } else if (code === 'VERIFICATION_REQUIRED') {
            _handleVerificationRequired(res.data, reject)
          } else {
            reject({ statusCode: res.statusCode, data: res.data })
          }
        } else {
          reject({ statusCode: res.statusCode, data: res.data })
        }
      },
      fail(err) {
        // Surface request id so callers / logger can correlate with
        // backend logs even on transport failures (timeout, DNS, TLS).
        reject({ statusCode: 0, data: err, requestId: requestId })
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
    content: sanitizeText(message),
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

// 遇到 PAYMENT_REQUIRED 弹窗提示（先保持简单形式，后续可附带跳转支付页的逻辑）
function _handlePaymentRequired(payload, reject) {
  const detail = payload && payload.detail
  const message = (detail && detail.message) || '订单尚未支付'
  wx.showModal({
    title: '订单尚未支付',
    content: sanitizeText(message),
    confirmText: '知道了',
    showCancel: false,
  })
  reject({ statusCode: 400, data: payload, handled: true })
}

// 遇到 VERIFICATION_REQUIRED 弹窗提示
function _handleVerificationRequired(payload, reject) {
  const detail = payload && payload.detail
  const message = (detail && detail.message) || '陪诊师资质未审核通过'
  wx.showModal({
    title: '资质审核中',
    content: sanitizeText(message),
    confirmText: '知道了',
    showCancel: false,
  })
  reject({ statusCode: 400, data: payload, handled: true })
}

function _handleUnauthorized(originalRequest, resolve, reject) {
  // Coalesce: if a refresh is already in flight, every concurrent 401 awaits
  // the same promise. On success, we re-fire the original request. On
  // failure, we propagate the same rejection to every waiter — nobody is
  // left hanging.
  _ensureRefresh().then(
    () => {
      // Token has been updated in storage by _ensureRefresh; just retry.
      request(originalRequest).then(resolve).catch(reject)
    },
    (err) => {
      reject(err)
    },
  )
}

function _ensureRefresh() {
  if (_refreshPromise) return _refreshPromise

  _refreshPromise = new Promise((resolveRefresh, rejectRefresh) => {
    const refreshToken = getRefreshToken()
    if (!refreshToken) {
      _forceLogout()
      rejectRefresh({ statusCode: 401, data: { detail: 'No refresh token' } })
      return
    }

    wx.request({
      url: config.API_BASE_URL + '/auth/refresh',
      method: 'POST',
      data: { refresh_token: refreshToken },
      header: { 'Content-Type': 'application/json' },
      success(res) {
        if (res.statusCode === 200 && res.data && res.data.access_token) {
          setAccessToken(res.data.access_token)
          setRefreshToken(res.data.refresh_token)
          resolveRefresh(res.data.access_token)
        } else {
          // Refresh server-rejected (e.g. token expired / revoked / reuse
          // detected). Force logout and propagate to every waiter.
          _forceLogout()
          rejectRefresh({ statusCode: res.statusCode, data: res.data })
        }
      },
      fail() {
        // Network failure during refresh. Previously this dropped every
        // queued caller on the floor (permanent pending). Now we reject
        // them all with a uniform error and let UI surface a retry hint.
        // We do NOT force-logout on a transient network blip — the user
        // can retry once connectivity returns.
        rejectRefresh({
          statusCode: 0,
          data: { detail: 'Network error during refresh' },
        })
      },
    })
  })

  // Always clear the cached promise after settle so the next 401 can start
  // a fresh refresh attempt (e.g. after the user reconnects).
  const clear = () => {
    _refreshPromise = null
  }
  _refreshPromise.then(clear, clear)
  return _refreshPromise
}

function _forceLogout() {
  clearTokens()
  const store = require('../store/index')
  store.reset()
  wx.reLaunch({ url: '/pages/login/index' })
}

module.exports = { request, _generateRequestId }
