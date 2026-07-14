const { logout } = require('../../../services/auth')
const { uploadAvatar } = require('../../../services/user')
const store = require('../../../store/index')
const router = require('../../../utils/router')
const i18n = require('../../../utils/i18n')
const i18nBehavior = require('../../../behaviors/i18n')

Page({
  behaviors: [i18nBehavior],
  data: {
    i18nScopes: ['common', 'profile', 'role', 'dialog'],
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
        wx.showLoading({ title: i18n.t('profile.uploading') })
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
            wx.showToast({ title: i18n.t('profile.avatarUpdated'), icon: 'success' })
          })
          .catch(() => {
            wx.hideLoading()
            wx.showToast({ title: i18n.t('profile.uploadFailed'), icon: 'none' })
          })
      }
    })
  },

  onBindPhone() {
    router.navigate({
      url: '/pages/profile/bind-phone/index'
    })
  },

  onMenuTap(e) {
    const target = e.currentTarget.dataset.target
    router.navigate({ url: target })
  },

  onLogout() {
    wx.showModal({
      title: i18n.t('dialog.tip'),
      content: i18n.t('profile.logoutConfirm'),
      confirmColor: '#1890FF',
      success: (res) => {
        if (res.confirm) {
          logout()
            .then(() => {
              store.setState({ user: null })
              router.relaunch({ url: '/pages/login/index' })
            })
            .catch(() => {
              store.setState({ user: null })
              router.relaunch({ url: '/pages/login/index' })
            })
        }
      }
    })
  }
})
