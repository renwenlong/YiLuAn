const { logout } = require('../../services/auth')
const store = require('../../store/index')

Page({
  data: {
    user: null
  },

  onLoad() {
    const state = store.getState()
    if (state && state.user) {
      this.setData({ user: state.user })
    }
  },

  onShow() {
    const state = store.getState()
    if (state && state.user) {
      this.setData({ user: state.user })
    }
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
