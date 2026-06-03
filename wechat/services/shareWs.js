/**
 * services/shareWs.js — 家属分享只读进度 WebSocket 业务薄壳
 * (S2-INT-003 / F2, ADR-0036 §2.4)
 *
 * 家属持 share_session 订阅订单实时进度（陪诊师位置 / 状态推送），**只读**：
 *   - 复用 core/ws-base（连接 / 指数退避重连 / 30s 心跳），与本人通知 WS 同源。
 *   - 鉴权走 onOpen 后首帧 {type:"share_auth", session:<share_session_jwt>}，
 *     token 不进 query string（避免被 nginx access log / 抓包记录）。
 *   - URL: WS_BASE_URL + /api/v1/ws/share/{token}（token = shareToken，URL 段；
 *     JWT 走 share_auth 首帧。后端会校验 JWT.tid === token_row.id 防换绑）。
 *
 * 与本人 notificationWs 的关键差异：
 *   - 凭证用 share_session（utils/shareSession），**绝不**用本人 access token。
 *   - 后端握手 ack 是 `share_auth_ok`（非 `auth_ok`），WSBase 只吞 auth_ok，
 *     故本壳自行吞掉 share_auth_ok，不向上抛。
 *   - 断线重连后后端会补发 {type:"location_replay", data:{...}}（最后已知位置），
 *     直接当一帧进度推给 UI，避免重连后地图空白。
 *   - 纯只读：本壳从不主动 send 业务帧（WSBase 只发 auth/ping）。任何上行非 ping
 *     帧后端会 4012 close——所以我们什么都不发。
 *
 * 关闭码语义（后端 ws.py，仅日志用，UI 不必区分）：
 *   4011 auth_timeout/invalid_auth_frame · 4001 invalid_session/token_mismatch
 *   4013 token_revoked_or_expired · 4014 per_token_cap_exceeded · 4002 idle_timeout
 */
const config = require('../config/index')
const { getShareSession, isShareSessionExpired } = require('../utils/shareSession')
const { WSBase } = require('../core/ws-base')
const logger = require('../utils/logger')

let _instance = null
let _progressCallback = null

function _getInstance() {
  if (_instance) return _instance
  _instance = new WSBase({
    // 首帧鉴权：每次（重）连懒解析 share_session，确保用的是最新一枚。
    // 返回 null（token 缺失/过期）→ WSBase 跳过首帧，后端 4011 关闭 → 触发重连，
    // 但重连同样拿不到有效 token，会一路退避到上限后停。上层应在 token 过期时先
    // 调 services/share.exchangeShareSession 重新静默换证，再 connect。
    authPayload: function () {
      if (isShareSessionExpired()) return null
      var session = getShareSession()
      if (!session) return null
      return { type: 'share_auth', session: session }
    },
  })
  _instance.on('message', function (data) {
    // pong / auth_ok 已被 WSBase 吞掉；share_auth_ok 是 share 专用 ack，这里吞掉。
    if (data && data.type === 'share_auth_ok') return
    // location_replay（重连补偿）与实时进度帧统一抛给上层，上层按 type 渲染。
    if (_progressCallback) _progressCallback(data)
  })
  _instance.on('error', function (err) {
    logger.warn('[shareWs] error', {
      err: (err && (err.errMsg || err.message)) || String(err),
    })
  })
  _instance.on('close', function (evt) {
    // 后端用关闭码表达 token 被 revoke / 过期 / 超额 / 闲置。这里只记录；
    // 4013/4001 这类「不可恢复」码理论上重连也救不回，但退避上限(5次)会自然收敛，
    // 不额外加分支以免与 WSBase 重连状态机打架。
    var code = evt && (evt.code != null ? evt.code : evt.errCode)
    logger.info('[shareWs] close', { code: code != null ? code : null })
  })
  _instance.on('reconnect', function (info) {
    logger.info('[shareWs] reconnect', { attempt: info.attempt, delay: info.delay })
  })
  return _instance
}

/**
 * 订阅某 shareToken 对应订单的只读进度。
 * @param {Object} options
 * @param {string} options.shareToken  分享 token（URL 段，非 JWT）
 * @param {Function} options.onProgress  收到进度/补偿帧的回调 (data) => void
 */
function connect(options) {
  options = options || {}
  if (options.onProgress) {
    _progressCallback = options.onProgress
  }
  var shareToken = options.shareToken
  if (!shareToken) {
    logger.warn('[shareWs] connect 缺 shareToken，跳过')
    return
  }
  // share_session 缺失/过期：不连。由上层先换证再 connect（见 authPayload 注释）。
  if (isShareSessionExpired() || !getShareSession()) {
    logger.warn('[shareWs] share_session 缺失/过期，跳过连接（上层应先换证）')
    return
  }

  var url =
    config.WS_BASE_URL + '/api/v1/ws/share/' + encodeURIComponent(shareToken)
  var inst = _getInstance()
  inst.connect(url)
}

function disconnect() {
  if (!_instance) return
  _instance.disconnect()
  _instance = null
  _progressCallback = null
}

module.exports = { connect: connect, disconnect: disconnect }
