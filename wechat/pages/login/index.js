const { wechatLogin } = require('../../services/auth')
const store = require('../../store/index')

Page({
  data: {
    loading: false
  },

  onLoad() {
    const state = store.getState()
    if (state && state.user && state.user.token) {
      if (state.user.role) {
        const home = state.user.role === 'patient' ? '/pages/patient/home/index' : '/pages/companion/home/index'
        wx.reLaunch({ url: home })
      } else {
        wx.redirectTo({ url: '/pages/role-select/index' })
      }
    }
  },

  onLogin() {
    if (this.data.loading) return
    this.setData({ loading: true })

    wechatLogin()
      .then(res => {
        const user = res.data || res
        store.setState({ user })
        if (user.role) {
          const home = user.role === 'patient' ? '/pages/patient/home/index' : '/pages/companion/home/index'
          wx.reLaunch({ url: home })
        } else {
          wx.redirectTo({ url: '/pages/role-select/index' })
        }
      })
      .catch(err => {
        console.error('登录失败', err)
        wx.showToast({ title: '登录失败，请重试', icon: 'none' })
      })
      .finally(() => {
        this.setData({ loading: false })
      })
  }
})
