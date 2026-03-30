var authService = require('../../../services/auth')
var sendOTP = authService.sendOTP
var bindPhone = authService.bindPhone
var validate = require('../../../utils/validate')
var isValidPhone = validate.isValidPhone
var isValidOTP = validate.isValidOTP
var store = require('../../../store/index')

Page({
  data: {
    phone: '',
    code: '',
    countdown: 0,
    sending: false,
    binding: false
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
          wx.navigateBack()
        }, 1500)
      })
      .catch(function () {
        wx.showToast({ title: '绑定失败', icon: 'none' })
      })
      .finally(function () {
        self.setData({ binding: false })
      })
  }
})
