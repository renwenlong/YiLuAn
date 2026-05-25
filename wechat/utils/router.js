/**
 * router.js — 统一封装 wx 路由跳转，便于：
 *   1) 集中加 trace 日志（线上排查“为什么跳到 login”）
 *   2) 后续接入埋点（navigation funnel / source tag）
 *   3) 单测里可 mock 一处而不是 77 处页面
 *
 * 设计：纯 facade，签名与 wx 原生保持一致；调用方可逐步迁移。
 *
 * @typedef {Object} NavOptions
 * @property {string} url           目标路由 / page path (以 / 开头)
 * @property {Function} [success]   wx success 回调
 * @property {Function} [fail]      wx fail 回调
 * @property {Function} [complete]  wx complete 回调
 *
 * @typedef {Object} BackOptions
 * @property {number} [delta]       返退页数，缺省 1
 *
 * @typedef {'navigateTo'|'redirectTo'|'reLaunch'|'switchTab'|'navigateBack'|'toLogin'} NavAction
 *
 * @typedef {(action: NavAction, options: object) => void} NavHook
 */

var _hooks = []
var _logger = null
function _getLogger() {
  // 懒加载避免潜在的循环依赖：router 是低层模块，logger 是叶子模块（不依赖 router），
  // 直接 require 也安全，但保留惰性获取语义以防未来 logger 变动。
  if (_logger) return _logger
  try { _logger = require('./logger') } catch (_) { _logger = null }
  return _logger
}

/**
 * 注册导航 hook，hook(action, options) 在跳转**之前**同步触发。
 * 不抛错（hook 异常被吞掉并 logger.warn），避免一处埋点把整个跳转拖死。
 *
 * @param {NavHook} hook
 * @returns {() => void} unsubscribe
 */
function onBeforeNavigate(hook) {
  if (typeof hook === 'function') _hooks.push(hook)
  return function unsubscribe() {
    var i = _hooks.indexOf(hook)
    if (i >= 0) _hooks.splice(i, 1)
  }
}

function _emit(action, options) {
  for (var i = 0; i < _hooks.length; i++) {
    try {
      _hooks[i](action, options)
    } catch (e) {
      var lg = _getLogger()
      if (lg) lg.warn('[router] hook error', { err: e && (e.message || String(e)) })
      else console.warn('[router] hook error:', e) // eslint-disable-line no-console
    }
  }
}

function _wxCall(method, options) {
  // wx 在测试 jsdom 下未必有该方法；返回值不重要
  if (typeof wx !== 'undefined' && typeof wx[method] === 'function') {
    return wx[method](options)
  }
  return undefined
}

/** @param {NavOptions} options */
function navigate(options) {
  _emit('navigateTo', options)
  return _wxCall('navigateTo', options)
}

/** @param {NavOptions} options */
function redirect(options) {
  _emit('redirectTo', options)
  return _wxCall('redirectTo', options)
}

/** @param {NavOptions} options */
function relaunch(options) {
  _emit('reLaunch', options)
  return _wxCall('reLaunch', options)
}

/** @param {NavOptions} options */
function switchTab(options) {
  _emit('switchTab', options)
  return _wxCall('switchTab', options)
}

/** @param {BackOptions} [options] */
function back(options) {
  var opts = options || {}
  _emit('navigateBack', opts)
  return _wxCall('navigateBack', opts)
}

/**
 * 跳转到登录页（最常见的强制下线场景，单独命名便于 grep + 埋点）。
 * @param {string} [reason] 下线原因 tag，缺省 'unknown'
 */
function toLogin(reason) {
  _emit('toLogin', { reason: reason || 'unknown' })
  return _wxCall('reLaunch', { url: '/pages/login/index' })
}

module.exports = {
  navigate: navigate,
  redirect: redirect,
  relaunch: relaunch,
  switchTab: switchTab,
  back: back,
  toLogin: toLogin,
  onBeforeNavigate: onBeforeNavigate,
  // 仅供测试 reset
  _clearHooks: function () { _hooks.length = 0 },
}
