const { logout } = require('../../services/auth')
const { uploadAvatar } = require('../../services/user')
const store = require('../../store/index')

Page({
  data: {
    user: null
  },

  onLoad() {
    this._refreshUser()
  },

  onShow() {
    this._refreshUser()
  },

  _refreshUser() {
    const state = store.getState()
    if (state && state.user) {
      var u = state.user
      this.setData({
        user: {
          name: u.display_name || u.name || '',
          avatar: u.avatar_url || u.avatar || '',
          phone: u.phone || '',
          role: u.role || ''
        }
      })
    }
  },

  onAvatarTap() {
    wx.chooseImage({
      count: 1,
      sizeType: ['compressed'],
      sourceType: ['album', 'camera'],
      success: (res) => {
        const filePath = res.tempFilePaths[0]
        wx.showLoading({ title: '上传中...' })
        uploadAvatar(filePath)
          .then((data) => {
            wx.hideLoading()
            var avatarUrl = data.avatar_url || data.avatar || data.url || ''
            if (avatarUrl) {
              var s = store.getState()
              var updated = Object.assign({}, s.user, { avatar_url: avatarUrl })
              store.setState({ user: updated })
              this._refreshUser()
            }
            wx.showToast({ title: '头像已更新', icon: 'success' })
          })
          .catch(() => {
            wx.hideLoading()
            wx.showToast({ title: '上传失败', icon: 'none' })
          })
      }
    })
  },

  onBindPhone() {
    wx.navigateTo({
      url: '/pages/profile/bind-phone/index'
    })
  },

  onMenuTap(e) {
    const target = e.currentTarget.dataset.target
    wx.navigateTo({ url: target })
  },

  onLogout() {
    wx.showModal({
      title: '提示',
      content: '确定要退出登录吗？',
      confirmColor: '#1890FF',
      success: (res) => {
        if (res.confirm) {
          logout()
            .then(() => {
              store.setState({ user: null })
              wx.reLaunch({ url: '/pages/login/index' })
            })
            .catch(() => {
              store.setState({ user: null })
              wx.reLaunch({ url: '/pages/login/index' })
            })
        }
      }
    })
  }
})
