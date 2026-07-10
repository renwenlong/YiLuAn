// behaviors/i18n.js
// I18N-DEV-002 — 页面级 i18n 注入 behavior（ADR-0063 §4.1）
//
// 用法（页面）：
//   const i18nBehavior = require('../../behaviors/i18n')
//   Page({ behaviors: [i18nBehavior], i18nScopes: ['common','settings','orderStatus'], ... })
//   wxml: {{t['common.confirm']}}   （静态文案，注入的扁平映射）
//   动态串仍在 js 层用 i18n.t(key, params) 现算后 setData。
//
// 机制：
//   - attached 时 subscribeSelector(selectLanguage, cb, { fireImmediately: true })
//     → AC-2.1：首屏即注入正确语言，不只在切换时刷。
//   - 语言变化 → setData({ t: buildScopedDict(scopes) }) 重新注入当前语言文案。
//   - detached 时 unsubscribe，防 store selector 泄漏（store 有 TTL warn）。
//
// 注：微信 Behavior 定义在主包，分包页面可 require 引用（AC-2 分包全覆盖）。

var store = require('../store/index')
var i18n = require('../utils/i18n')

module.exports = Behavior({
  // 页面可覆写 data.i18nScopes 指定注入哪些 namespace（不写则全量注入）
  data: {
    t: {}
  },

  lifetimes: {
    attached: function () {
      var self = this
      var scopes = (this.data && this.data.i18nScopes) || null
      // fireImmediately: true → 首屏即注入当前语言（AC-2.1）
      this._i18nUnsub = store.subscribeSelector(
        store.selectLanguage,
        function () {
          self.setData({ t: i18n.buildScopedDict(scopes) })
        },
        { fireImmediately: true }
      )
    },
    detached: function () {
      if (typeof this._i18nUnsub === 'function') {
        this._i18nUnsub()
        this._i18nUnsub = null
      }
    }
  },

  methods: {
    // 页面 js 层动态串（带占位）用：this.$t('otp.sentTo', { phone })
    $t: function (key, params) {
      return i18n.t(key, params)
    }
  }
})
