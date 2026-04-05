var userService = require('../../../services/user')
var authService = require('../../../services/auth')
var validate = require('../../../utils/validate')
var store = require('../../../store/index')

Page({
  data: {
    nickname: '',
    avatarUrl: '',
    showPhoneSection: true,
    phone: '',
    code: '',
    countdown: 0,
    sending: false,
    saving: false
  },

  onChooseAvatar: function () {
    var self = this
    wx.chooseImage({
      count: 1,
      sizeType: ['compressed'],
      sourceType: ['album', 'camera'],
      success: function (res) {
        var filePath = res.tempFilePaths[0]
        wx.showLoading({ title: '上传中...' })
        userService.uploadAvatar(filePath)
          .then(function (data) {
            wx.hideLoading()
            var url = data.avatar_url || data.url || ''
            if (url) {
              self.setData({ avatarUrl: url })
              var state = store.getState()
              var user = Object.assign({}, state.user, { avatar_url: url })
              store.setState({ user: user })
            }
            wx.showToast({ title: '头像已上传', icon: 'success' })
          })
          .catch(function () {
            wx.hideLoading()
            wx.showToast({ title: '上传失败', icon: 'none' })
          })
      }
    })
  },

  onNicknameInput: function (e) {
    this.setData({ nickname: e.detail.value })
  },

  onPhoneInput: function (e) {
    this.setData({ phone: e.detail.value })
  },

  onCodeInput: function (e) {
    this.setData({ code: e.detail.value })
  },

  onSendOTP: function () {
    var phone = this.data.phone.trim()
    if (!validate.isValidPhone(phone)) {
      wx.showToast({ title: '请输入正确的手机号', icon: 'none' })
      return
    }
    this.setData({ sending: true })
    var self = this
    authService.sendOTP(phone)
      .then(function () {
        self.setData({ sending: false, countdown: 60 })
        self.startCountdown()
        wx.showToast({ title: '验证码已发送', icon: 'success' })
      })
      .catch(function () {
        self.setData({ sending: false })
        wx.showToast({ title: '发送失败，请重试', icon: 'none' })
      })
  },

  startCountdown: function () {
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

  onUnload: function () {
    if (this._timer) {
      clearInterval(this._timer)
    }
  },

  onSubmit: function () {
    var nickname = this.data.nickname.trim()
    if (!nickname) {
      wx.showToast({ title: '请输入昵称', icon: 'none' })
      return
    }

    var phone = this.data.phone.trim()
    if (!phone || !validate.isValidPhone(phone)) {
      wx.showToast({ title: '请输入正确的手机号', icon: 'none' })
      return
    }

    var code = this.data.code.trim()
    if (!code || !validate.isValidOTP(code)) {
      wx.showToast({ title: '请输入6位验证码', icon: 'none' })
      return
    }

    this.setData({ saving: true })
    var self = this

    userService.updateMe({ display_name: nickname })
      .then(function () {
        var state = store.getState()
        var user = Object.assign({}, state.user, { display_name: nickname })
        store.setState({ user: user })

        return authService.bindPhone(phone, code)
          .then(function () {
            var s = store.getState()
            store.setState({ user: Object.assign({}, s.user, { phone: phone }) })
          })
      })
      .then(function () {
        self.setData({ saving: false })
        var state = store.getState()
        var role = (state.user && state.user.role) || 'patient'
        var home = role === 'patient' ? '/pages/patient/home/index' : '/pages/companion/home/index'
        wx.reLaunch({ url: home })
      })
      .catch(function () {
        self.setData({ saving: false })
        wx.showToast({ title: '保存失败，请重试', icon: 'none' })
      })
  },

  onSkip: function () {
    var state = store.getState()
    var role = (state.user && state.user.role) || 'patient'
    var home = role === 'patient' ? '/pages/patient/home/index' : '/pages/companion/home/index'
    wx.reLaunch({ url: home })
  }
})
