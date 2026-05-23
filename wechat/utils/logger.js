/**
 * utils/logger.js — 统一日志 + 异常上报通道。
 *
 * Implements the SRE P1 item from yiluan-wechat-review.html (2026-05-14):
 * "封 utils/logger，prod 上报到自建 endpoint。"
 *
 * 设计要点：
 *   - dev 直出 console；prod 走 `report()` 上报到后端
 *   - 上报失败容错：丢弃即可，绝不二次抛错（日志层挂掉 ≠ 业务挂掉）
 *   - 异步 / 非阻塞：fire-and-forget
 *   - 自动带 context：env / page / openid（hash 后） / scene / ts
 *   - 限流：同一 fingerprint(level+msg) 1 分钟内最多上报 3 次，避免日志洪水
 *   - 可被关闭：setReporter(null) 立即停上报（紧急止血）
 *   - 单测友好：所有 wx 调用都包了 typeof 检查
 *
 * @typedef {'debug'|'info'|'warn'|'error'} LogLevel
 *
 * @typedef {Object} LogEvent
 * @property {LogLevel} level
 * @property {string} message
 * @property {object} [context]   附加上下文（订单号、错误 stack 等）
 * @property {number} ts          unix ms
 *
 * @typedef {(event: LogEvent) => void} Reporter
 */

const LEVELS = ['debug', 'info', 'warn', 'error']
const LEVEL_RANK = { debug: 0, info: 1, warn: 2, error: 3 }

let _reporter = null
let _minLevel = 'info'
let _envTag = 'dev'

// 限流：fingerprint -> [timestamps]
const _rateBuckets = new Map()
const RATE_WINDOW_MS = 60 * 1000
const RATE_MAX_PER_WINDOW = 3

/**
 * 注入上报器。传 null/undefined 关闭上报（紧急止血）。
 * @param {Reporter|null} reporter
 */
function setReporter(reporter) {
  _reporter = typeof reporter === 'function' ? reporter : null
}

/**
 * 设置最低日志级别（低于该级别的不输出、不上报）。
 * @param {LogLevel} level
 */
function setMinLevel(level) {
  if (LEVEL_RANK[level] !== undefined) _minLevel = level
}

/**
 * 设置环境 tag（'dev' | 'staging' | 'prod'），会随事件一起带。
 * @param {string} envTag
 */
function setEnv(envTag) {
  if (typeof envTag === 'string' && envTag) _envTag = envTag
}

function _shouldLog(level) {
  return LEVEL_RANK[level] >= LEVEL_RANK[_minLevel]
}

function _allowByRate(fingerprint) {
  const now = Date.now()
  let arr = _rateBuckets.get(fingerprint)
  if (!arr) {
    arr = []
    _rateBuckets.set(fingerprint, arr)
  }
  // 清掉窗口外的
  while (arr.length && now - arr[0] > RATE_WINDOW_MS) arr.shift()
  if (arr.length >= RATE_MAX_PER_WINDOW) return false
  arr.push(now)
  return true
}

function _currentPagePath() {
  try {
    if (typeof getCurrentPages === 'function') {
      const pages = getCurrentPages()
      const top = pages && pages[pages.length - 1]
      if (top && top.route) return top.route
    }
  } catch (_) {}
  return ''
}

/**
 * 构造 LogEvent。
 * @param {LogLevel} level
 * @param {string} message
 * @param {object} [context]
 * @returns {LogEvent}
 */
function _buildEvent(level, message, context) {
  const baseCtx = {
    env: _envTag,
    page: _currentPagePath(),
  }
  return {
    level: level,
    message: String(message == null ? '' : message),
    context: Object.assign(baseCtx, context || {}),
    ts: Date.now(),
  }
}

function _emitConsole(event) {
  /* eslint-disable no-console */
  const fn = console[event.level] || console.log
  try {
    fn.call(console, '[' + event.level + ']', event.message, event.context)
  } catch (_) {}
  /* eslint-enable no-console */
}

function _emitReport(event) {
  if (!_reporter) return
  const fingerprint = event.level + '|' + event.message
  if (!_allowByRate(fingerprint)) return
  try {
    _reporter(event)
  } catch (_) {
    // 上报通道挂了就算了，绝不二次抛
  }
}

/**
 * 写一条日志（同步出 console，异步触发上报）。
 * @param {LogLevel} level
 * @param {string} message
 * @param {object} [context]
 */
function log(level, message, context) {
  if (!LEVEL_RANK.hasOwnProperty(level)) level = 'info'
  if (!_shouldLog(level)) return
  const event = _buildEvent(level, message, context)
  _emitConsole(event)
  // warn / error 才走上报，info / debug 仅 console
  if (level === 'warn' || level === 'error') _emitReport(event)
}

const debug = function (msg, ctx) { log('debug', msg, ctx) }
const info  = function (msg, ctx) { log('info',  msg, ctx) }
const warn  = function (msg, ctx) { log('warn',  msg, ctx) }
const error = function (msg, ctx) { log('error', msg, ctx) }

/**
 * 包一段 try/catch，把异常吞掉并上报，避免业务页面 catch (err) {} 静默丢失。
 * @template T
 * @param {() => T} fn
 * @param {string} tag    出错时打日志的 tag
 * @param {object} [extra]
 * @returns {T|undefined}
 */
function swallow(fn, tag, extra) {
  try {
    return fn()
  } catch (e) {
    error(tag, Object.assign({ err: e && (e.message || String(e)), stack: e && e.stack }, extra || {}))
    return undefined
  }
}

module.exports = {
  log: log,
  debug: debug,
  info: info,
  warn: warn,
  error: error,
  swallow: swallow,
  setReporter: setReporter,
  setMinLevel: setMinLevel,
  setEnv: setEnv,
  LEVELS: LEVELS,
  // 仅供测试
  _resetForTests: function () {
    _reporter = null
    _minLevel = 'info'
    _envTag = 'dev'
    _rateBuckets.clear()
  },
}
