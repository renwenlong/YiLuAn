const { wechatLogin, sendOTP, verifyOTP } = require('../../services/auth')
const validate = require('../../utils/validate')
const store = require('../../store/index')
const router = require('../../utils/router')
const logger = require('../../utils/logger')
const i18n = require('../../utils/i18n')
const i18nBehavior = require('../../behaviors/i18n')

Page({
  behaviors: [i18nBehavior],
  data: {
    // i18nBehavior 注入范围（静态文案）
    i18nScopes: ['common', 'login'],
    loading: false,
    showPhoneLogin: false,
    phone: '',
    code: '',
    sendingOTP: false,
    countdown: 0,
    agreed: false
  },

  onLoad() {
    const state = store.getState()
    if (state && state.user && state.user.token) {
      if (state.user.role) {
        if (!state.user.display_name) {
          router.redirect({ url: '/pages/profile/setup/index' })
        } else {
          const home = state.user.role === 'patient' ? '/pages/patient/home/index' : '/pages/companion/home/index'
          router.relaunch({ url: home })
        }
      } else {
        router.redirect({ url: '/pages/role-select/index' })
      }
    }
  },

  onUnload() {
    if (this._timer) {
      clearInterval(this._timer)
    }
  },

  // ---- 微信登录 ----
  onLogin() {
    if (!this.data.agreed) {
      wx.showToast({ title: i18n.t('toast.agreeFirst'), icon: 'none' })
      return
    }
    if (this.data.loading) return
    this.setData({ loading: true })

    wechatLogin()
      .then(user => {
        this._navigateAfterLogin(user)
      })
      .catch(err => {
        logger.error('Login failed', logger.errorContext(err))
        wx.showToast({ title: i18n.t('toast.loginFailed'), icon: 'none' })
      })
      .finally(() => {
        this.setData({ loading: false })
      })
  },

  // ---- 手机号登录 ----
  onPhoneInput(e) {
    this.setData({ phone: e.detail.value })
  },

  onCodeInput(e) {
    this.setData({ code: e.detail.value })
  },

  onSendOTP() {
    var phone = this.data.phone.trim()
    if (!validate.isValidPhone(phone)) {
      wx.showToast({ title: i18n.t('toast.invalidPhone'), icon: 'none' })
      return
    }
    this.setData({ sendingOTP: true })
    var self = this
    sendOTP(phone)
      .then(function () {
        self.setData({ sendingOTP: false, countdown: 60 })
        self._startCountdown()
        wx.showToast({ title: i18n.t('toast.codeSent'), icon: 'success' })
      })
      .catch(function () {
        self.setData({ sendingOTP: false })
        wx.showToast({ title: i18n.t('toast.sendFailed'), icon: 'none' })
      })
  },

  _startCountdown() {
    var self = this
    self._timer = setInterval(function () {
      var count = self.data.countdown - 1
      if (count <= 0) {
        clearInterval(self._timer)
        self.setData({ countdown: 0 })
      } else {
        self.setData({ countdown: count })
      }
    }, 1000)
  },

  onPhoneLogin() {
    if (!this.data.agreed) {
      wx.showToast({ title: i18n.t('toast.agreeFirst'), icon: 'none' })
      return
    }
    var phone = this.data.phone.trim()
    if (!validate.isValidPhone(phone)) {
      wx.showToast({ title: i18n.t('toast.invalidPhone'), icon: 'none' })
      return
    }
    var code = this.data.code.trim()
    if (!validate.isValidOTP(code)) {
      wx.showToast({ title: i18n.t('toast.inputCode6'), icon: 'none' })
      return
    }

    if (this.data.loading) return
    this.setData({ loading: true })
    var self = this

    verifyOTP(phone, code)
      .then(function (user) {
        self._navigateAfterLogin(user)
      })
      .catch(function (err) {
        logger.error('Login failed', Object.assign(logger.errorContext(err), { phase: 'verifyOTP' }))
        wx.showToast({ title: i18n.t('toast.codeWrongExpired'), icon: 'none' })
      })
      .finally(function () {
        self.setData({ loading: false })
      })
  },

  // ---- 切换登录方式 ----
  onSwitchLoginMode() {
    this.setData({ showPhoneLogin: !this.data.showPhoneLogin })
  },

  // ---- 协议勾选 ----
  onToggleAgreement() {
    this.setData({ agreed: !this.data.agreed })
  },

  onOpenTerms() {
    router.navigate({ url: '/pages/legal/terms/index' })
  },

  onOpenPrivacy() {
    router.navigate({ url: '/pages/legal/privacy/index' })
  },

  // ---- 登录后路由 ----
  _navigateAfterLogin(user) {
    if (user.role) {
      if (!user.display_name) {
        router.redirect({ url: '/pages/profile/setup/index' })
      } else {
        var home = user.role === 'patient' ? '/pages/patient/home/index' : '/pages/companion/home/index'
        router.relaunch({ url: home })
      }
    } else {
      router.redirect({ url: '/pages/role-select/index' })
    }
  }
})
