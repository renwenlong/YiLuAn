/**
 * utils/analytics.js — 业务漏斗 / 行为埋点封装。
 *
 * 5 节点核心漏斗（小程序端患者下单链路）：
 *   1. funnel.companion_list_view        浏览陪诊列表
 *   2. funnel.companion_detail_view      进入陪诊详情
 *   3. funnel.order_create_start         发起下单（进入下单页）
 *   4. funnel.order_submit               提交订单（API success）
 *   5. funnel.payment_success            支付成功（pay-result 落地）
 *
 * 设计要点
 *   - 复用 logger 的 reporter 通道，但走自己的 emit() 接口：funnel 事件需要
 *     即便 level=info 也要上报（logger 默认只上报 warn / error）。
 *   - 提供 funnel.<step> 命名空间常量 FUNNEL_STEPS，禁止业务层手拼字符串。
 *   - 不收 PII：调 emit() 时由上层保证 payload 不含手机号 / 姓名等；
 *     额外做一道防御：剥掉看起来像 phone / id_card / name 的 key（白名单外）。
 *   - 不抛错：fire-and-forget，业务页面调 trackFunnel(step, {...}) 不需要 catch。
 *   - 限流：同一 step 5 秒内最多一次（避免 onShow 重复触发刷屏）。
 *
 * @typedef {Object} FunnelEvent
 * @property {string} event_type
 * @property {object} payload
 * @property {object} client_meta
 * @property {number} ts
 */

// 5 节点 funnel step → event_type 字典。业务层一律 require 这个常量，
// 不要手拼字符串，避免漏斗节点错位。
var FUNNEL_STEPS = {
  COMPANION_LIST_VIEW:   'funnel.companion_list_view',
  COMPANION_DETAIL_VIEW: 'funnel.companion_detail_view',
  ORDER_CREATE_START:    'funnel.order_create_start',
  ORDER_SUBMIT:          'funnel.order_submit',
  PAYMENT_SUCCESS:       'funnel.payment_success',
}

// 漏斗节点白名单（防止拼错字符串绕过常量）
var _FUNNEL_WHITELIST = {}
Object.keys(FUNNEL_STEPS).forEach(function (k) { _FUNNEL_WHITELIST[FUNNEL_STEPS[k]] = true })

// payload 中允许出现的 key（白名单外的会被静默剥掉）—— 进一步降低 PII 泄漏面。
// 业务侧需要带其他字段时，先在这里 review 一遍。
var _PAYLOAD_KEY_WHITELIST = {
  step: true,
  service_type: true,
  order_id: true,
  companion_id: true,
  hospital_id: true,
  amount_cents: true,
  scene: true,
  source: true,
  duration_ms: true,
  filter: true,
  position: true,
  list_size: true,
}

// 同 step 限流，避免 onShow 重复触发
var _lastEmitMs = {}
var FUNNEL_THROTTLE_MS = 5 * 1000

// 用户注入的 emitter；默认 null，app.onLaunch 里 setEmitter 上 reporter
var _emitter = null

// 默认 client_meta（env 等），app.onLaunch 调 setClientMeta 设置
var _clientMeta = { env: 'dev' }

/**
 * 注入上报器。
 * @param {(event:FunnelEvent)=>void|null} emitter
 */
function setEmitter(emitter) {
  _emitter = typeof emitter === 'function' ? emitter : null
}

/**
 * 设置随事件一起带的 client_meta（env / sdk_version / scene 等）。
 * 不会覆盖未提供的 key，merge 风格。
 * @param {object} meta
 */
function setClientMeta(meta) {
  if (meta && typeof meta === 'object') {
    Object.keys(meta).forEach(function (k) { _clientMeta[k] = meta[k] })
  }
}

function _currentPagePath() {
  try {
    if (typeof getCurrentPages === 'function') {
      var pages = getCurrentPages()
      var top = pages && pages[pages.length - 1]
      if (top && top.route) return top.route
    }
  } catch (_) {}
  return ''
}

/**
 * 过滤 payload：仅保留白名单 key，并把 string 类型字段做 PII 兜底（手机号/身份证 mask）。
 * 不在白名单的 key 直接丢弃 —— 业务层若有新字段，先加到 _PAYLOAD_KEY_WHITELIST。
 */
function _sanitizePayload(payload) {
  var out = {}
  if (!payload || typeof payload !== 'object') return out
  Object.keys(payload).forEach(function (k) {
    if (!_PAYLOAD_KEY_WHITELIST[k]) return
    var v = payload[k]
    if (typeof v === 'string') {
      // 万一业务层把手机号塞进 source / filter 这类自由字段，做 mask 兜底
      v = v.replace(/\b1[3-9]\d{9}\b/g, '1**********')
      v = v.replace(/\b\d{17}[\dXx]\b/g, '***ID18***')
      v = v.replace(/\b\d{15}\b/g, '***ID15***')
    }
    out[k] = v
  })
  return out
}

/**
 * 上报一个 funnel 节点。
 * @param {string} step    必须是 FUNNEL_STEPS 中的某个值
 * @param {object} [payload]
 */
function trackFunnel(step, payload) {
  if (!_FUNNEL_WHITELIST[step]) {
    // 不在白名单内的直接丢弃，避免业务手拼错字符串污染 funnel
    return
  }
  var now = Date.now()
  if (_lastEmitMs[step] && now - _lastEmitMs[step] < FUNNEL_THROTTLE_MS) {
    return
  }
  _lastEmitMs[step] = now
  if (!_emitter) return
  var event = {
    event_type: step,
    payload: _sanitizePayload(payload),
    client_meta: Object.assign({ page: _currentPagePath() }, _clientMeta),
    ts: now,
  }
  try {
    _emitter(event)
  } catch (_) {
    // fire-and-forget
  }
}

/**
 * 通用埋点（非漏斗 / 通用 event）。事件名同样落到 telemetry_events，
 * 用于 logger 二次封装 / A/B 实验 / 业务自定义。
 * @param {string} eventType
 * @param {object} [payload]
 */
function track(eventType, payload) {
  if (typeof eventType !== 'string' || !eventType) return
  if (!_emitter) return
  var event = {
    event_type: eventType,
    payload: _sanitizePayload(payload),
    client_meta: Object.assign({ page: _currentPagePath() }, _clientMeta),
    ts: Date.now(),
  }
  try {
    _emitter(event)
  } catch (_) {}
}

module.exports = {
  FUNNEL_STEPS: FUNNEL_STEPS,
  trackFunnel: trackFunnel,
  track: track,
  setEmitter: setEmitter,
  setClientMeta: setClientMeta,
  // tests-only
  _resetForTests: function () {
    _emitter = null
    _clientMeta = { env: 'dev' }
    _lastEmitMs = {}
  },
}
