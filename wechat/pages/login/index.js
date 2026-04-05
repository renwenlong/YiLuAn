const { wechatLogin, sendOTP, verifyOTP } = require('../../services/auth')
const validate = require('../../utils/validate')
const store = require('../../store/index')

Page({
  data: {
    loading: false,
    showPhoneLogin: false,
    phone: '',
    code: '',
    sendingOTP: false,
    countdown: 0
  },

  onLoad() {
    const state = store.getState()
    if (state && state.user && state.user.token) {
      if (state.user.role) {
        if (!state.user.display_name) {
          wx.redirectTo({ url: '/pages/profile/setup/index' })
        } else {
          const home = state.user.role === 'patient' ? '/pages/patient/home/index' : '/pages/companion/home/index'
          wx.reLaunch({ url: home })
        }
      } else {
        wx.redirectTo({ url: '/pages/role-select/index' })
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
    if (this.data.loading) return
    this.setData({ loading: true })

    wechatLogin()
      .then(user => {
        this._navigateAfterLogin(user)
      })
      .catch(err => {
        console.error('登录失败', err)
        wx.showToast({ title: '登录失败，请重试', icon: 'none' })
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
      wx.showToast({ title: '请输入正确的手机号', icon: 'none' })
      return
    }
    this.setData({ sendingOTP: true })
    var self = this
    sendOTP(phone)
      .then(function () {
        self.setData({ sendingOTP: false, countdown: 60 })
        self._startCountdown()
        wx.showToast({ title: '验证码已发送', icon: 'success' })
      })
      .catch(function () {
        self.setData({ sendingOTP: false })
        wx.showToast({ title: '发送失败，请重试', icon: 'none' })
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
    var phone = this.data.phone.trim()
    if (!validate.isValidPhone(phone)) {
      wx.showToast({ title: '请输入正确的手机号', icon: 'none' })
      return
    }
    var code = this.data.code.trim()
    if (!validate.isValidOTP(code)) {
      wx.showToast({ title: '请输入6位验证码', icon: 'none' })
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
        console.error('登录失败', err)
        wx.showToast({ title: '验证码错误或已过期', icon: 'none' })
      })
      .finally(function () {
        self.setData({ loading: false })
      })
  },

  // ---- 切换登录方式 ----
  onSwitchLoginMode() {
    this.setData({ showPhoneLogin: !this.data.showPhoneLogin })
  },

  // ---- 登录后路由 ----
  _navigateAfterLogin(user) {
    if (user.role) {
      if (!user.display_name) {
        wx.redirectTo({ url: '/pages/profile/setup/index' })
      } else {
        var home = user.role === 'patient' ? '/pages/patient/home/index' : '/pages/companion/home/index'
        wx.reLaunch({ url: home })
      }
    } else {
      wx.redirectTo({ url: '/pages/role-select/index' })
    }
  }
})
