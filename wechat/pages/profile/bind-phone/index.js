var authService = require('../../../services/auth')
var sendOTP = authService.sendOTP
var bindPhone = authService.bindPhone
var validate = require('../../../utils/validate')
var isValidPhone = validate.isValidPhone
var isValidOTP = validate.isValidOTP
var store = require('../../../store/index')
const router = require('../../../utils/router')

Page({
  data: {
    phone: '',
    code: '',
    countdown: 0,
    sending: false,
    binding: false,
    redirect: ''
  },

  onLoad: function (options) {
    if (options && options.redirect) {
      this.setData({ redirect: decodeURIComponent(options.redirect) })
    }
  },

  onPhoneInput: function (e) {
    this.setData({ phone: e.detail.value })
  },

  onCodeInput: function (e) {
    this.setData({ code: e.detail.value })
  },

  onSendOTP: function () {
    if (!isValidPhone(this.data.phone)) {
      wx.showToast({ title: '请输入正确手机号', icon: 'none' })
      return
    }
    var self = this
    self.setData({ sending: true })
    sendOTP(self.data.phone)
      .then(function () {
        wx.showToast({ title: '验证码已发送', icon: 'success' })
        self.startCountdown()
      })
      .catch(function () {
        wx.showToast({ title: '发送失败', icon: 'none' })
      })
      .finally(function () {
        self.setData({ sending: false })
      })
  },

  startCountdown: function () {
    var self = this
    self.setData({ countdown: 60 })
    var timer = setInterval(function () {
      if (self.data.countdown <= 1) {
        clearInterval(timer)
        self.setData({ countdown: 0 })
        return
      }
      self.setData({ countdown: self.data.countdown - 1 })
    }, 1000)
  },

  onBind: function () {
    if (!isValidPhone(this.data.phone) || !isValidOTP(this.data.code)) {
      wx.showToast({ title: '请检查输入', icon: 'none' })
      return
    }
    var self = this
    self.setData({ binding: true })
    bindPhone(self.data.phone, self.data.code)
      .then(function () {
        var state = store.getState()
        var user = Object.assign({}, state.user, { phone: self.data.phone })
        store.setState({ user: user })
        wx.showToast({ title: '绑定成功', icon: 'success' })
        setTimeout(function () {
          if (self.data.redirect) {
            router.redirect({ url: self.data.redirect })
          } else {
            router.back()
          }
        }, 1500)
      })
      .catch(function (err) {
        wx.showToast({ title: _bindErrorMessage(err), icon: 'none', duration: 2500 })
      })
      .finally(function () {
        self.setData({ binding: false })
      })
  }
})

// 将后端 400/409 的真实原因透出为中文提示，不再笼统“绑定失败”。
// 后端 detail 可能是纯 string（无 error_code）或 { message } 对象。
function _bindErrorMessage(err) {
  var detail = err && err.data && err.data.detail
  var raw = ''
  if (typeof detail === 'string') {
    raw = detail
  } else if (detail && typeof detail === 'object') {
    raw = detail.message || ''
  }
  var map = {
    'OTP code expired or not found': '验证码已过期或未发送，请重新获取',
    'Invalid OTP code': '验证码错误，请检查后重试',
    'User already has a phone number bound': '该账号已绑定手机号',
    'Phone number already registered to another account': '该手机号已被其他账号注册'
  }
  if (raw && map[raw]) {
    return map[raw]
  }
  // 未命中映射：有后端文案就显示后端文案，否则兑底。
  return raw || '绑定失败，请稍后重试'
}

// 仅供单测 require（小程序运行时 module 存在，不影响 Page 注册）。
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { _bindErrorMessage: _bindErrorMessage }
}
