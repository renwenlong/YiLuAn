// utils/i18n.js
// I18N-DEV-002 — 微信端 i18n 运行时（ADR-0063 §4.1）
//
// 职责：
//   1. 持有主字典（docs/i18n/dictionary.json 的镜像，见下方 require 说明）
//   2. t(key, params?) — 按点分 key 取当前语言文案，具名占位 {name} 替换
//   3. 语言判定：getCurrentLang / setLang / resolveDefaultLang（Storage + 系统语言）
//
// 设计原则（顺 fontScale.js 的 CommonJS `var` 风格）：
//   - 纯逻辑模块，不直接 setData（注入由 i18nBehavior 负责）
//   - 当前语言真源挂 store.language，本模块 getCurrentLang 读 store，避免双源
//   - 字典为人读 SSoT docs/i18n/dictionary.json；小程序不能 require 仓库根的
//     JSON，故本目录维护一份 dict 对象镜像（key 集与主字典强制一致，DEV-001
//     产出为准）。后续可加构建步同步，本期手工对齐（与主字典同 PR 核对）。

var store = require('../store/index')
var logger = null
function _log(level, msg, ctx) {
  if (logger === null) {
    try { logger = require('./logger') } catch (e) { logger = false }
  }
  if (logger) logger[level](msg, ctx)
}

var STORAGE_KEY = 'language'
/** @type {Array<'zh-Hans'|'en'>} */
var SUPPORTED = ['zh-Hans', 'en']
/** @type {'zh-Hans'|'en'} */
var DEFAULT_LANG = 'zh-Hans'

// ── 主字典镜像（key 集 == docs/i18n/dictionary.json，DEV-001 SSoT）──────────
// 结构：{ namespace: { key: { 'zh-Hans': '中', 'en': 'EN', _params?: [...] } } }
var DICT = require('./i18n.dict.js')

/**
 * 归一化语言码：zh* → zh-Hans，其余 → en。
 * @param {string} raw 系统/存储原始语言码
 * @returns {'zh-Hans'|'en'}
 */
function normalizeLang(raw) {
  if (!raw) return DEFAULT_LANG
  var s = String(raw).toLowerCase()
  if (s.indexOf('zh') === 0) return 'zh-Hans'
  return 'en'
}

/**
 * 当前语言：真源为 store.language；未设置回退 DEFAULT_LANG。
 * @returns {'zh-Hans'|'en'}
 */
function getCurrentLang() {
  var st = store.getState()
  var lang = st && st.language
  if (SUPPORTED.indexOf(lang) === -1) return DEFAULT_LANG
  return lang
}

/**
 * FR-2 默认语言判定：Storage 有值用之，无值取系统语言，写回 Storage。
 * app.js onLaunch 调用，结果 setState 到 store.language。
 * @returns {'zh-Hans'|'en'}
 */
function resolveDefaultLang() {
  var stored
  try { stored = wx.getStorageSync(STORAGE_KEY) } catch (e) { stored = '' }
  if (SUPPORTED.indexOf(stored) !== -1) return stored
  var sys = ''
  try {
    var info = wx.getSystemInfoSync()
    sys = info && info.language
  } catch (e) { sys = '' }
  var lang = normalizeLang(sys)
  try { wx.setStorageSync(STORAGE_KEY, lang) } catch (e) {}
  return lang
}

/**
 * 切换语言：更新 store.language + 持久化 Storage。
 * store.language 变化会触发 i18nBehavior 的 subscribeSelector 重新注入。
 * @param {'zh-Hans'|'en'} lang
 */
function setLang(lang) {
  if (SUPPORTED.indexOf(lang) === -1) {
    _log('warn', '[i18n] setLang unsupported, ignored', { lang: lang })
    return
  }
  try { wx.setStorageSync(STORAGE_KEY, lang) } catch (e) {}
  store.setState({ language: lang })
}

/**
 * 点分 key 取字典条目 → 当前语言文案 → 占位替换。
 * @param {string} key 如 'orderStatus.created' / 'otp.sentTo'
 * @param {Object} [params] 具名占位值，如 { phone: '138...' }
 * @returns {string} 命中返回译文；未命中返回 key 本身（并 warn，便于抽检发现遗漏）
 */
function t(key, params) {
  if (!key) return ''
  var lang = getCurrentLang()
  var parts = String(key).split('.')
  var node = DICT
  for (var i = 0; i < parts.length; i++) {
    if (node && typeof node === 'object' && node[parts[i]] !== undefined) {
      node = node[parts[i]]
    } else {
      node = undefined
      break
    }
  }
  if (!node || typeof node !== 'object' || node[lang] === undefined) {
    _log('warn', '[i18n] missing key', { key: key, lang: lang })
    return key
  }
  var text = node[lang]
  if (params) {
    text = text.replace(/\{(\w+)\}/g, function (m, name) {
      return params[name] !== undefined ? String(params[name]) : m
    })
  }
  return text
}

/**
 * 为指定 namespace 列表构建当前语言的扁平 { leafKey: text } 映射，
 * 供 i18nBehavior 一次性 setData({ t: {...} })，wxml 用 {{t.xxx}} 绑定。
 * 仅处理静态（无占位）条目；带占位的动态串在页面 js 层用 t(key, params) 现算。
 * @param {string[]} namespaces 如 ['common','settings','orderStatus']
 * @returns {Object} { 'common.confirm': '确认', ... } 扁平映射（当前语言）
 */
function buildScopedDict(namespaces) {
  var lang = getCurrentLang()
  var out = {}
  var nsList = namespaces && namespaces.length ? namespaces : Object.keys(DICT)
  for (var n = 0; n < nsList.length; n++) {
    var ns = nsList[n]
    var group = DICT[ns]
    if (!group || typeof group !== 'object') continue
    var keys = Object.keys(group)
    for (var k = 0; k < keys.length; k++) {
      var leaf = group[keys[k]]
      if (leaf && typeof leaf === 'object' && leaf[lang] !== undefined) {
        // 静态条目才注入扁平表；带占位的（_params）跳过，交页面 js 层现算
        if (!leaf._params) {
          out[ns + '.' + keys[k]] = leaf[lang]
        }
      }
    }
  }
  return out
}

module.exports = {
  t: t,
  setLang: setLang,
  getCurrentLang: getCurrentLang,
  resolveDefaultLang: resolveDefaultLang,
  normalizeLang: normalizeLang,
  buildScopedDict: buildScopedDict,
  SUPPORTED: SUPPORTED,
  DEFAULT_LANG: DEFAULT_LANG,
  STORAGE_KEY: STORAGE_KEY
}
