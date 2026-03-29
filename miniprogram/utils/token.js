const ACCESS_TOKEN_KEY = 'yiluan_access_token'
const REFRESH_TOKEN_KEY = 'yiluan_refresh_token'

function getAccessToken() {
  try {
    return wx.getStorageSync(ACCESS_TOKEN_KEY) || null
  } catch (e) {
    return null
  }
}

function setAccessToken(token) {
  wx.setStorageSync(ACCESS_TOKEN_KEY, token)
}

function getRefreshToken() {
  try {
    return wx.getStorageSync(REFRESH_TOKEN_KEY) || null
  } catch (e) {
    return null
  }
}

function setRefreshToken(token) {
  wx.setStorageSync(REFRESH_TOKEN_KEY, token)
}

function clearTokens() {
  wx.removeStorageSync(ACCESS_TOKEN_KEY)
  wx.removeStorageSync(REFRESH_TOKEN_KEY)
}

function isTokenExpired(token) {
  if (!token) return true
  try {
    const parts = token.split('.')
    if (parts.length !== 3) return true
    const payload = JSON.parse(decodeBase64(parts[1]))
    if (!payload.exp) return true
    // expired if current time >= exp (seconds)
    return Date.now() >= payload.exp * 1000
  } catch (e) {
    return true
  }
}

function decodeBase64(str) {
  // Handle URL-safe base64
  let base64 = str.replace(/-/g, '+').replace(/_/g, '/')
  // Pad with '='
  while (base64.length % 4 !== 0) {
    base64 += '='
  }
  // Decode (works in Mini Program JS environment)
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/='
  let output = ''
  for (let i = 0; i < base64.length; i += 4) {
    const a = chars.indexOf(base64[i])
    const b = chars.indexOf(base64[i + 1])
    const c = chars.indexOf(base64[i + 2])
    const d = chars.indexOf(base64[i + 3])
    output += String.fromCharCode((a << 2) | (b >> 4))
    if (c !== 64) output += String.fromCharCode(((b & 15) << 4) | (c >> 2))
    if (d !== 64) output += String.fromCharCode(((c & 3) << 6) | d)
  }
  return output
}

module.exports = {
  getAccessToken,
  setAccessToken,
  getRefreshToken,
  setRefreshToken,
  clearTokens,
  isTokenExpired,
}
