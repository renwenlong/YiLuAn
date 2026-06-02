// shareSession.js — 家属分享态 share_session JWT 存储 (S2-INT-003 / F2)
//
// share_session 与下单人自己的 access/refresh token 是**两套独立凭证**：
//   - access/refresh (utils/token.js) = 下单人本人登录态，长 TTL
//   - share_session                   = 家属只读视图态，30min 短 TTL，单订单作用域
//
// 二者必须分开存：家属端落地页持 share_session 拉脱敏视图 / 订 WS，
// 绝不能污染或复用本人 access token（ADR-0036 §2.2）。

const SHARE_SESSION_KEY = 'yiluan_share_session'
const SHARE_SESSION_EXP_KEY = 'yiluan_share_session_exp'

function getShareSession() {
  try {
    return wx.getStorageSync(SHARE_SESSION_KEY) || null
  } catch (e) {
    return null
  }
}

// expiresAt: ISO string (后端 share_session_expires_at) — 存毫秒时间戳便于本地预判过期
function setShareSession(token, expiresAt) {
  wx.setStorageSync(SHARE_SESSION_KEY, token)
  if (expiresAt) {
    const ms = typeof expiresAt === 'number' ? expiresAt : Date.parse(expiresAt)
    if (!Number.isNaN(ms)) {
      wx.setStorageSync(SHARE_SESSION_EXP_KEY, ms)
    }
  }
}

function clearShareSession() {
  wx.removeStorageSync(SHARE_SESSION_KEY)
  wx.removeStorageSync(SHARE_SESSION_EXP_KEY)
}

// 本地预判：share_session 是否已过期 / 缺失。早一拍触发重新静默换证，
// 避免拿着死 JWT 撞 401 才反应。无 token / 无 exp 一律视为过期。
function isShareSessionExpired() {
  const token = getShareSession()
  if (!token) return true
  let exp
  try {
    exp = wx.getStorageSync(SHARE_SESSION_EXP_KEY)
  } catch (e) {
    return true
  }
  if (!exp) return true
  return Date.now() >= exp
}

module.exports = {
  getShareSession,
  setShareSession,
  clearShareSession,
  isShareSessionExpired,
  SHARE_SESSION_KEY,
  SHARE_SESSION_EXP_KEY,
}
