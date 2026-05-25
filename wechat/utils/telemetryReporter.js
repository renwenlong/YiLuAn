/**
 * utils/telemetryReporter.js — 把 logger / analytics 事件打到后端
 * `POST /api/v1/telemetry/events`。
 *
 * 设计要点
 *   - 用裸 wx.request，不走 services/api.js：上报通道绝不能因为 token
 *     过期 / 401 refresh 风暴等业务逻辑被拖垮（services/api.js 里有
 *     refresh / guard 弹窗等副作用）。
 *   - 不阻塞业务：fail / 非 2xx 全部静默丢弃。
 *   - Bearer token 可带可不带：服务端允许匿名上报（首页埋点会先于登录）。
 *   - 不抛错，不二次上报错误（不能让上报失败再触发上报，避免无限递归）。
 *   - 与 logger.js 的事件结构对齐：logger 的 LogEvent {level,message,context,ts}
 *     需要包装成 telemetry 的 {event_type,payload,client_meta,ts}。
 *   - analytics 的 FunnelEvent 已经是 telemetry 形状，直接透传。
 */
var config = require('../config/index')
var token = require('./token')

var ENDPOINT = '/telemetry/events'

/**
 * 构造一个 reporter 函数，给 logger.setReporter 用。
 * 输入是 logger 的 LogEvent，输出是 POST 到 telemetry。
 * @returns {(event: object) => void}
 */
function buildLoggerReporter() {
  return function (logEvent) {
    if (!logEvent) return
    // 把 logger 事件包成 telemetry 事件
    var payload = {}
    // logger 的 context 里可能含 stack、err 等，全部塞进 payload；上层
    // logger 已经过 PII rate-limit + fingerprint；后端 schema 还会
    // 做一道 PII regex 拒绝。这里不再二次清洗。
    if (logEvent.context && typeof logEvent.context === 'object') {
      Object.keys(logEvent.context).forEach(function (k) {
        // page / env 等 meta 字段单独提到 client_meta
        if (k === 'page' || k === 'env') return
        payload[k] = logEvent.context[k]
      })
    }
    if (logEvent.message) payload.message = String(logEvent.message).slice(0, 1024)
    var clientMeta = {}
    if (logEvent.context) {
      if (logEvent.context.page) clientMeta.page = logEvent.context.page
      if (logEvent.context.env) clientMeta.env = logEvent.context.env
    }
    var event = {
      event_type: 'logger.' + (logEvent.level || 'info'),
      payload: payload,
      client_meta: clientMeta,
      ts: logEvent.ts || Date.now(),
    }
    _post(event)
  }
}

/**
 * 构造一个 emitter 函数，给 analytics.setEmitter 用。analytics 事件
 * 已经是 telemetry 形状（event_type / payload / client_meta / ts），
 * 直接透传。
 * @returns {(event: object) => void}
 */
function buildAnalyticsEmitter() {
  return function (event) {
    if (!event || !event.event_type) return
    _post(event)
  }
}

function _post(event) {
  if (typeof wx === 'undefined' || !wx.request) return
  var header = { 'Content-Type': 'application/json' }
  try {
    var t = token.getAccessToken && token.getAccessToken()
    if (t) header['Authorization'] = 'Bearer ' + t
  } catch (_) {}
  try {
    wx.request({
      url: config.API_BASE_URL + ENDPOINT,
      method: 'POST',
      data: event,
      header: header,
      timeout: 5000,
      // 全部丢弃，绝不抛错 / 不二次上报
      success: function () {},
      fail: function () {},
    })
  } catch (_) {
    // ignore
  }
}

module.exports = {
  buildLoggerReporter: buildLoggerReporter,
  buildAnalyticsEmitter: buildAnalyticsEmitter,
  // tests-only
  _endpoint: ENDPOINT,
}
