var store = require('../../../store/index')
const router = require('../../../utils/router')
var { sendOTP } = require('../../../services/auth')
var { deleteAccount } = require('../../../services/user')
var { clearTokens } = require('../../../utils/token')
const i18n = require('../../../utils/i18n')
const i18nBehavior = require('../../../behaviors/i18n')

Page({
  behaviors: [i18nBehavior],
  data: {
    i18nScopes: ['common', 'deleteAccount'],
    phone: '',
    phoneMask: '',
    code: '',
    confirmed: false,
    canSubmit: false,
    countdown: 0,
    submitting: false,
    pressing: false,
    pressCountdown: 3
  },

  _timer: null,
  _pressTimer: null,
  _pressInterval: null,

  onLoad: function () {
    var state = store.getState()
    if (state && state.user && state.user.phone) {
      var phone = state.user.phone
      var mask = phone.slice(0, 3) + '****' + phone.slice(-4)
      this.setData({ phone: phone, phoneMask: mask })
    }
  },

  onUnload: function () {
    if (this._timer) {
      clearInterval(this._timer)
      this._timer = null
    }
    this._clearPress()
  },

  onCodeInput: function (e) {
    this.setData({ code: e.detail.value })
    this._updateCanSubmit()
  },

  onToggleConfirm: function () {
    this.setData({ confirmed: !this.data.confirmed })
    this._updateCanSubmit()
  },

  _updateCanSubmit: function () {
    var canSubmit = this.data.confirmed && this.data.code.length === 6
    this.setData({ canSubmit: canSubmit })
  },

  onSendCode: function () {
    var self = this
    if (self.data.countdown > 0) return
    if (!self.data.phone) {
      wx.showToast({ title: i18n.t('deleteAccount.noPhone'), icon: 'none' })
      return
    }

    wx.showLoading({ title: i18n.t('deleteAccount.sending') })
    sendOTP(self.data.phone)
      .then(function () {
        wx.hideLoading()
        wx.showToast({ title: i18n.t('deleteAccount.codeSent'), icon: 'none' })
        self.setData({ countdown: 60 })
        self._timer = setInterval(function () {
          var c = self.data.countdown - 1
          self.setData({ countdown: c })
          if (c <= 0) {
            clearInterval(self._timer)
            self._timer = null
          }
        }, 1000)
      })
      .catch(function () {
        wx.hideLoading()
        wx.showToast({ title: i18n.t('deleteAccount.sendFailed'), icon: 'none' })
      })
  },

  onPressStart: function () {
    var self = this
    if (!self.data.canSubmit || self.data.submitting) return

    self.setData({ pressing: true, pressCountdown: 3 })

    self._pressInterval = setInterval(function () {
      var next = self.data.pressCountdown - 1
      if (next <= 0) {
        self._clearPress()
        self.setData({ pressing: false, pressCountdown: 3 })
        self._doDelete()
      } else {
        self.setData({ pressCountdown: next })
      }
    }, 1000)
  },

  onPressEnd: function () {
    if (!this.data.pressing) return
    this._clearPress()
    this.setData({ pressing: false, pressCountdown: 3 })
  },

  _clearPress: function () {
    if (this._pressTimer) {
      clearTimeout(this._pressTimer)
      this._pressTimer = null
    }
    if (this._pressInterval) {
      clearInterval(this._pressInterval)
      this._pressInterval = null
    }
  },

  _doDelete: function () {
    var self = this
    self.setData({ submitting: true })
    wx.showLoading({ title: i18n.t('deleteAccount.deleting') })

    deleteAccount(self.data.code)
      .then(function () {
        wx.hideLoading()
        clearTokens()
        store.reset()
        wx.showToast({ title: i18n.t('deleteAccount.deleted'), icon: 'success', duration: 2000 })
        setTimeout(function () {
          router.relaunch({ url: '/pages/login/index' })
        }, 1500)
      })
      .catch(function (err) {
        wx.hideLoading()
        self.setData({ submitting: false })
        var msg = i18n.t('deleteAccount.deleteFailed')
        if (err && err.data && err.data.detail) {
          msg = err.data.detail
        }
        wx.showToast({ title: msg, icon: 'none' })
      })
  },

  onCancel: function () {
    router.back()
  }
})
