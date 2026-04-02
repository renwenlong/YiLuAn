const { switchRole } = require('../../../services/user')
const { setAccessToken, setRefreshToken } = require('../../../utils/token')
const store = require('../../../store/index')

Page({
  data: {
    cacheSize: '0 KB',
    user: null
  },

  onLoad: function () {
    this.calcCache()
    var state = store.getState()
    if (state && state.user) {
      this.setData({ user: state.user })
    }
  },

  onShow: function () {
    var state = store.getState()
    if (state && state.user) {
      this.setData({ user: state.user })
    }
  },

  calcCache: function () {
    var info = wx.getStorageInfoSync()
    this.setData({ cacheSize: (info.currentSize || 0) + ' KB' })
  },

  onSwitchRole: function () {
    var user = this.data.user
    if (!user || !user.roles || user.roles.length < 2) return
    var targetRole = user.role === 'patient' ? 'companion' : 'patient'
    var targetLabel = targetRole === 'patient' ? '患者' : '陪诊师'
    wx.showModal({
      title: '切换角色',
      content: '确定切换为' + targetLabel + '吗？',
      confirmColor: '#1890FF',
      success: function (res) {
        if (res.confirm) {
          wx.showLoading({ title: '切换中...' })
          switchRole(targetRole)
            .then(function (data) {
              wx.hideLoading()
              setAccessToken(data.access_token)
              setRefreshToken(data.refresh_token)
              store.setState({ user: data.user })
              var home = targetRole === 'patient' ? '/pages/patient/home/index' : '/pages/companion/home/index'
              wx.reLaunch({ url: home })
            })
            .catch(function () {
              wx.hideLoading()
              wx.showToast({ title: '切换失败', icon: 'none' })
            })
        }
      }
    })
  },

  onClearCache: function () {
    var self = this
    wx.showModal({
      title: '提示',
      content: '确定清除缓存？',
      success: function (res) {
        if (res.confirm) {
          wx.clearStorageSync()
          self.setData({ cacheSize: '0 KB' })
          wx.showToast({ title: '已清除', icon: 'success' })
        }
      }
    })
  },

  onAbout: function () {
    wx.navigateTo({ url: '/pages/profile/about/index' })
  }
})
