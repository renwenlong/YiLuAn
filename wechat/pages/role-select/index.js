const { updateMe } = require('../../services/user')
const { getCompanionStats } = require('../../services/companion')
const store = require('../../store/index')

Page({
  data: {
    loading: false
  },

  onLoad(options) {
    if (options && options.target) {
      this._addRole(options.target)
    }
  },

  onSelectRole(e) {
    const role = e.currentTarget.dataset.role
    this._addRole(role)
  },

  _addRole(role) {
    if (this.data.loading) return
    this.setData({ loading: true })
    var self = this

    updateMe({ role })
      .then(res => {
        const state = store.getState()
        const oldRoles = (state.user && state.user.roles) || []
        var newRoles = oldRoles.slice()
        if (newRoles.indexOf(role) === -1) {
          newRoles.push(role)
        }
        const user = Object.assign({}, state.user, { role: role, roles: newRoles })
        store.setState({ user: user })
        if (!user.display_name) {
          wx.redirectTo({ url: '/pages/profile/setup/index' })
          return
        }
        if (role === 'companion') {
          self._checkCompanionProfile()
        } else {
          wx.reLaunch({ url: '/pages/patient/home/index' })
        }
      })
      .catch(err => {
        console.error('设置角色失败', err)
        wx.showToast({ title: '操作失败，请重试', icon: 'none' })
      })
      .finally(() => {
        self.setData({ loading: false })
      })
  },

  _checkCompanionProfile() {
    getCompanionStats()
      .then(function () {
        wx.reLaunch({ url: '/pages/companion/home/index' })
      })
      .catch(function () {
        wx.redirectTo({ url: '/pages/companion/setup/index' })
      })
  }
})
