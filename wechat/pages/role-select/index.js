const { updateMe } = require('../../services/user')
const { getCompanionStats } = require('../../services/companion')
const store = require('../../store/index')
const router = require('../../utils/router')
const logger = require('../../utils/logger')
const i18n = require('../../utils/i18n')
const i18nBehavior = require('../../behaviors/i18n')

Page({
  behaviors: [i18nBehavior],
  data: {
    i18nScopes: ['common', 'role'],
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
          router.redirect({ url: '/pages/profile/setup/index' })
          return
        }
        if (role === 'companion') {
          self._checkCompanionProfile()
        } else {
          router.relaunch({ url: '/pages/patient/home/index' })
        }
      })
      .catch(err => {
        logger.error('Failed to set role', { err: err && (err.message || String(err)) })
        wx.showToast({ title: i18n.t('toast.opFailed'), icon: 'none' })
      })
      .finally(() => {
        self.setData({ loading: false })
      })
  },

  _checkCompanionProfile() {
    getCompanionStats()
      .then(function () {
        router.relaunch({ url: '/pages/companion/home/index' })
      })
      .catch(function () {
        router.redirect({ url: '/pages/companion/setup/index' })
      })
  }
})
