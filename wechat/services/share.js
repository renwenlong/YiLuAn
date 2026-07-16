// services/share.js — 家属端微信静默分享 (S2-INT-003 / F2, ADR-0036 §2.2)
//
// 流程 (微信小程序静默路径):
//   家属点分享链接 → 落地页拿到 shareToken
//     → wx.login 静默授权 (只取 openid, 零摩擦, 不要 phone)
//     → POST /shares/{token}/session  { wx_openid }  换 share_session JWT(30min)
//     → GET  /shares/session/order    Bearer <share_session>  拉脱敏只读视图
//
// 关键边界:
//   - share_session 与本人 access token 严格隔离 (utils/shareSession.js)，
//     家属端**绝不**带本人 Authorization，只带 share_session bearer。
//   - 过期/被 revoke 的 token → 后端 401；本地先用 isShareSessionExpired 预判。
//   - openid 由后端从 wx.login code2session 解析；本客户端把 code 提交给
//     /session，staging 需配置真实 WECHAT_APP_ID/SECRET。

const config = require('../config/index')
const { request } = require('./api')
const {
  getShareSession,
  setShareSession,
  clearShareSession,
  isShareSessionExpired,
} = require('../utils/shareSession')

// share_session 专用裸 request：不复用 services/api.js（那条链路会注入本人
// access token 并跑 401 refresh，对家属态有害）。这里只认 share_session bearer。
function _shareRequest({ url, method = 'GET', data, shareSession }) {
  return new Promise((resolve, reject) => {
    const header = { 'Content-Type': 'application/json' }
    if (shareSession) {
      header['Authorization'] = 'Bearer ' + shareSession
    }
    wx.request({
      url: config.API_BASE_URL + '/' + url,
      method,
      data,
      header,
      timeout: 15000,
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data)
        } else {
          const err = new Error('share request failed: ' + res.statusCode)
          err.statusCode = res.statusCode
          err.body = res.data
          reject(err)
        }
      },
      fail(e) {
        reject(e)
      },
    })
  })
}

// wx.login 静默授权 → code。包一层 Promise，失败显式 reject（不静默吞）。
function _wxLoginCode() {
  return new Promise((resolve, reject) => {
    wx.login({
      success(res) {
        if (res && res.code) {
          resolve(res.code)
        } else {
          reject(new Error('wx.login: empty code'))
        }
      },
      fail(e) {
        reject(e)
      },
    })
  })
}

// 用 token + 微信静默 code 换 share_session JWT，存入隔离存储。
// 返回 { share_scope, order_id, share_session_expires_at }（不外泄 JWT 串）。
function exchangeShareSession(shareToken) {
  if (!shareToken) {
    return Promise.reject(new Error('shareToken required'))
  }
  return _wxLoginCode().then(code =>
    _shareRequest({
      url: 'shares/' + shareToken + '/session',
      method: 'POST',
      data: { wx_openid: code },
    }).then(resp => {
      setShareSession(resp.share_session, resp.share_session_expires_at)
      return {
        share_scope: resp.share_scope,
        order_id: resp.order_id,
        share_session_expires_at: resp.share_session_expires_at,
      }
    })
  )
}

// 拉脱敏只读订单视图。share_session 缺失/过期则先静默换证再拉。
function getShareOrder(shareToken, { forceRefresh = false } = {}) {
  const needExchange = forceRefresh || isShareSessionExpired()
  const ensure = needExchange
    ? exchangeShareSession(shareToken)
    : Promise.resolve()
  return ensure
    .then(() =>
      _shareRequest({
        url: 'shares/session/order',
        method: 'GET',
        shareSession: getShareSession(),
      })
    )
    .catch(err => {
      // 401 = token 过期/被 revoke/被篡改。若不是刚换的证，重换一次再试。
      if (err && err.statusCode === 401 && !needExchange) {
        clearShareSession()
        return exchangeShareSession(shareToken).then(() =>
          _shareRequest({
            url: 'shares/session/order',
            method: 'GET',
            shareSession: getShareSession(),
          })
        )
      }
      throw err
    })
}

// ============================================================================
// 发起端 (Owner 路径) — 患者本人为订单创建/管理家属分享
// ADR-0036 §F2 / ANDROID-DEV-WX-SHARE-ENTRY
//
// 与接收端(家属)严格区分：发起端走本人 access token(services/api.js request),
// **不用** share_session。对齐 iOS ShareService.createShare/listShares/revokeShare。
// 端点：
//   POST   /orders/{order_id}/shares          创建分享 → CreateShareResponse
//   GET    /orders/{order_id}/shares          active 列表 → ListSharesResponse
//   DELETE /orders/{order_id}/shares/{token_id} 撤销单个 token
// 后端约束：同订单 active token 上限 3，第 4 个自动 revoke 最老一枚。
// ============================================================================

// 患者端为订单创建分享链接。scope: 'full' | 'progress_only'。
// 返回 CreateShareResponse：{ id, share_token, share_url, share_scope,
//   share_expires_at, share_active_count, ... }。
function createShare(orderId, scope = 'full') {
  if (!orderId) {
    return Promise.reject(new Error('orderId required'))
  }
  return request({
    url: 'orders/' + orderId + '/shares',
    method: 'POST',
    data: { share_scope: scope },
  })
}

// 患者端查询订单当前 active 分享列表。
// 返回 ListSharesResponse：{ items: [...], share_active_count }。
function listShares(orderId) {
  if (!orderId) {
    return Promise.reject(new Error('orderId required'))
  }
  return request({
    url: 'orders/' + orderId + '/shares',
    method: 'GET',
  })
}

// 患者端撤销单个分享 token（按 token 行 UUID）。
// 触发服务端 WS close 4013 / 已发 viewer session 失效。
function revokeShare(orderId, tokenId) {
  if (!orderId || !tokenId) {
    return Promise.reject(new Error('orderId and tokenId required'))
  }
  return request({
    url: 'orders/' + orderId + '/shares/' + tokenId,
    method: 'DELETE',
  })
}

module.exports = {
  // 接收端 (家属静默授权)
  exchangeShareSession,
  getShareOrder,
  // 发起端 (患者本人 Owner 路径)
  createShare,
  listShares,
  revokeShare,
  // 暴露给测试 / WS 模块复用
  _shareRequest,
  _wxLoginCode,
}
