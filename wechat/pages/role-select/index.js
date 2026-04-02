const { updateMe } = require('../../services/user')
const store = require('../../store/index')

Page({
  data: {
    loading: false
  },

  onSelectRole(e) {
    const role = e.currentTarget.dataset.role
    if (this.data.loading) return
    this.setData({ loading: true })

    updateMe({ role })
      .then(res => {
        const state = store.getState()
        const user = Object.assign({}, state.user, { role })
        store.setState({ user: user })
        if (!user.display_name) {
          wx.redirectTo({ url: '/pages/profile/setup/index' })
        } else {
          const home = role === 'patient' ? '/pages/patient/home/index' : '/pages/companion/home/index'
          wx.reLaunch({ url: home })
        }
      })
      .catch(err => {
        console.error('设置角色失败', err)
        wx.showToast({ title: '操作失败，请重试', icon: 'none' })
      })
      .finally(() => {
        this.setData({ loading: false })
      })
  }
})
