/**
 * router.js — 统一封装 wx 路由跳转，便于：
 *   1) 集中加 trace 日志（线上排查"为什么跳到 login"）
 *   2) 后续接入埋点（navigation funnel / source tag）
 *   3) 单测里可 mock 一处而不是 77 处页面
 *
 * 设计：纯 facade，签名与 wx 原生保持一致；调用方可逐步迁移。
 * Quick Win (评审 2026-05-14)：本期只把基础设施层 (auth.logout /
 * api._forceLogout) 迁过来，UI 页面的 77 处调用渐进迁移。
 */

var _hooks = []

/**
 * 注册导航 hook，hook(action, options) 在跳转**之前**同步触发。
 * 不抛错（hook 异常被吞掉并 console.warn），避免一处埋点把整个跳转拖死。
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
      console.warn('[router] hook error:', e)
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

function navigate(options) {
  _emit('navigateTo', options)
  return _wxCall('navigateTo', options)
}

function redirect(options) {
  _emit('redirectTo', options)
  return _wxCall('redirectTo', options)
}

function relaunch(options) {
  _emit('reLaunch', options)
  return _wxCall('reLaunch', options)
}

function switchTab(options) {
  _emit('switchTab', options)
  return _wxCall('switchTab', options)
}

function back(options) {
  var opts = options || {}
  _emit('navigateBack', opts)
  return _wxCall('navigateBack', opts)
}

/** 跳转到登录页（最常见的强制下线场景，单独命名便于 grep + 埋点）。 */
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
