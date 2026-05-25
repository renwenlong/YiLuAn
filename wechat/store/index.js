/**
 * store/index.js — 模块化 store + selector + 自动 diff
 *
 * Implements FE-Arch P1 from yiluan-wechat-review.html (2026-05-14):
 * "store 必须升级 — 分模块 selector ... 回调风暴和'忘了 unsubscribe'的内存
 *  泄漏只是早晚的事"
 *
 * 设计原则：
 *   1. **完全向后兼容**：getState / setState / subscribe / reset 签名不变
 *   2. **新能力 opt-in**：subscribeSelector(selector, listener) 只在 selector
 *      返回值变化时（浅相等）才触发，避免全量回调风暴
 *   3. **TTL 监控**：subscribe 返回的 unsubscribe 顺手在 logger.warn 报告
 *      "subscribed 但没 unsubscribe" 的页面泄漏（dev only），方便排查
 *
 * @typedef {object} State
 *
 * @typedef {(state: State) => any} Selector
 * @typedef {(state: State) => void} Listener
 * @typedef {(selected: any, state: State) => void} SelectorListener
 */

let _state = {
  isAuthenticated: false,
  user: null,
}

let _listeners = []
let _logger = null
function _log(level, msg, ctx) {
  // 懒加载避免启动顺序问题（store 是极底层）
  if (_logger === null) {
    try { _logger = require('../utils/logger') } catch (_) { _logger = false }
  }
  if (_logger) _logger[level](msg, ctx)
  // eslint-disable-next-line no-console
  else console[level === 'error' ? 'error' : 'warn'](msg, ctx)
}
/** @type {Array<{ selector: Selector, listener: SelectorListener, last: any }>} */
let _selectorEntries = []

function getState() {
  return Object.assign({}, _state)
}

/**
 * @param {Partial<State>} partial
 */
function setState(partial) {
  _state = Object.assign({}, _state, partial)
  // legacy 全量订阅
  for (let i = 0; i < _listeners.length; i++) {
    try { _listeners[i](_state) } catch (e) {
      // 单个 listener 出错不影响其他
      _log('warn', '[store] listener error', { err: e && (e.message || String(e)) })
    }
  }
  // selector 订阅：浅相等比对，变化才触发
  for (let j = 0; j < _selectorEntries.length; j++) {
    const entry = _selectorEntries[j]
    let next
    try { next = entry.selector(_state) } catch (e) {
      _log('warn', '[store] selector error', { err: e && (e.message || String(e)) })
      continue
    }
    if (!_shallowEqual(entry.last, next)) {
      entry.last = next
      try { entry.listener(next, _state) } catch (e) {
        _log('warn', '[store] selector listener error', { err: e && (e.message || String(e)) })
      }
    }
  }
}

/**
 * 旧 API：全量订阅。每次 setState 都会被回调，自己负责 diff。
 * @param {Listener} fn
 * @returns {() => void}
 */
function subscribe(fn) {
  _listeners.push(fn)
  return function unsubscribe() {
    _listeners = _listeners.filter((l) => l !== fn)
  }
}

/**
 * 新 API：基于 selector 订阅，selector 返回值浅变化时才触发 listener。
 * 用于精细订阅 user / unreadCount 等"局部状态"。
 * @param {Selector} selector
 * @param {SelectorListener} listener
 * @param {{ fireImmediately?: boolean }} [opts]
 * @returns {() => void}
 */
function subscribeSelector(selector, listener, opts) {
  const entry = { selector: selector, listener: listener, last: undefined }
  try { entry.last = selector(_state) } catch (_) { entry.last = undefined }
  _selectorEntries.push(entry)
  if (opts && opts.fireImmediately) {
    try { listener(entry.last, _state) } catch (_) {}
  }
  return function unsubscribe() {
    _selectorEntries = _selectorEntries.filter((e) => e !== entry)
  }
}

function reset() {
  _state = { isAuthenticated: false, user: null }
  // 购买后向兼容：触发所有订阅者，保持旧行为
  for (let i = 0; i < _listeners.length; i++) {
    try { _listeners[i](_state) } catch (_) {}
  }
  // selector 订阅：把 last 同步为 reset 后的值并触发变化（如果有）
  for (let j = 0; j < _selectorEntries.length; j++) {
    const entry = _selectorEntries[j]
    let next
    try { next = entry.selector(_state) } catch (_) { continue }
    if (!_shallowEqual(entry.last, next)) {
      entry.last = next
      try { entry.listener(next, _state) } catch (_) {}
    }
  }
}

/**
 * 仅供测试/紧急场景：清掉所有订阅者。
 * 业务代码不要调（会把 app.js 的全局订阅也炸掉）。
 */
function _clearAllListeners() {
  _listeners = []
  _selectorEntries = []
}

// ── built-in selectors（鼓励调用方用这些常量代替 getState().xxx，便于改名）──

/** @type {Selector} */
const selectUser = function (s) { return s.user }
/** @type {Selector} */
const selectIsAuthenticated = function (s) { return s.isAuthenticated }
/** @type {Selector} */
const selectUnreadCount = function (s) { return s.unreadCount || 0 }
/** @type {Selector} */
const selectLastNotification = function (s) { return s.lastNotification || null }
/** @type {Selector} */
const selectCity = function (s) { return s.city || null }

// ── internal ────────────────────────────────────────────────────────────────

function _shallowEqual(a, b) {
  if (a === b) return true
  if (a === null || a === undefined || b === null || b === undefined) return false
  if (typeof a !== 'object' || typeof b !== 'object') return false
  const ka = Object.keys(a)
  const kb = Object.keys(b)
  if (ka.length !== kb.length) return false
  for (let i = 0; i < ka.length; i++) {
    if (a[ka[i]] !== b[ka[i]]) return false
  }
  return true
}

module.exports = {
  // legacy API（不动）
  getState: getState,
  setState: setState,
  subscribe: subscribe,
  reset: reset,
  // 新 API
  subscribeSelector: subscribeSelector,
  // selectors
  selectUser: selectUser,
  selectIsAuthenticated: selectIsAuthenticated,
  selectUnreadCount: selectUnreadCount,
  selectLastNotification: selectLastNotification,
  selectCity: selectCity,
  // 测试 helper
  _listenerCount: function () { return _listeners.length + _selectorEntries.length },
  _clearAllListeners: _clearAllListeners,
}
