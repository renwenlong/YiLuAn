const { switchRole } = require('../../../services/user')
const { setAccessToken, setRefreshToken } = require('../../../utils/token')
const { getHospitalFilters, getNearestRegion } = require('../../../services/hospital')
const store = require('../../../store/index')
const router = require('../../../utils/router')
const i18n = require('../../../utils/i18n')
const i18nBehavior = require('../../../behaviors/i18n')

Page({
  behaviors: [i18nBehavior],
  data: {
    // i18nBehavior 注入范围（静态文案）
    i18nScopes: ['common', 'settings', 'city'],
    cacheSize: '0 KB',
    user: null,
    city: '',
    showCityPicker: false,
    showLangPicker: false,
    allCities: [],
    locating: false,
    // 动态拼接 label（随语言/角色变，onShow/语言切换时重算）
    switchRoleLabel: '',
    currentRoleLabel: '',
    langLabel: '',
    currentLang: 'zh-Hans'
  },

  // 动态 label 集中重算（占位串在 js 层用 $t 现算）
  _recalcI18nLabels: function () {
    var user = this.data.user
    var lang = i18n.getCurrentLang()
    var patchData = {
      currentLang: lang,
      langLabel: lang === 'en' ? this.$t('settings.languageEn') : this.$t('settings.languageZh')
    }
    if (user) {
      var isPatient = user.role === 'patient'
      var targetRole = isPatient ? this.$t('role.companion') : this.$t('role.patient')
      var curRole = isPatient ? this.$t('role.patient') : this.$t('role.companion')
      patchData.switchRoleLabel = this.$t('role.switchTo', { targetRole: targetRole })
      patchData.currentRoleLabel = this.$t('role.current', { role: curRole })
    }
    this.setData(patchData)
  },

  onLoad: function () {
    this.calcCache()
    var state = store.getState()
    if (state && state.user) {
      this.setData({ user: state.user })
    }
    if (state && state.city) {
      this.setData({ city: state.city })
    }
  },

  onShow: function () {
    var state = store.getState()
    if (state && state.user) {
      this.setData({ user: state.user })
    }
    if (state && state.city) {
      this.setData({ city: state.city })
    }
    this._recalcI18nLabels()
  },

  // 语言入口 (AC-4)
  onLanguageTap: function () {
    this.setData({ showLangPicker: true })
  },

  onCloseLangPicker: function () {
    this.setData({ showLangPicker: false })
  },

  onSelectLang: function (e) {
    var lang = e.currentTarget.dataset.lang
    i18n.setLang(lang)
    this.setData({ showLangPicker: false })
    // i18nBehavior 会因 store.language 变化重注入静态 t；动态 label 手动重算
    this._recalcI18nLabels()
  },

  calcCache: function () {
    var info = wx.getStorageInfoSync()
    this.setData({ cacheSize: (info.currentSize || 0) + ' KB' })
  },

  onCityTap: function () {
    var self = this
    self.setData({ showCityPicker: true })
    if (self.data.allCities.length === 0) {
      getHospitalFilters({})
        .then(function (res) {
          self.setData({ allCities: res.cities || [] })
        })
        .catch(function () {
          self.setData({ allCities: [] })
        })
    }
  },

  onCloseCityPicker: function () {
    this.setData({ showCityPicker: false })
  },

  onAutoLocate: function () {
    var self = this
    if (self.data.locating) return
    self.setData({ locating: true })
    wx.authorize({
      scope: 'scope.userFuzzyLocation',
      success: function () {
        wx.getFuzzyLocation({
          type: 'wgs84',
          success: function (res) {
            getNearestRegion(res.latitude, res.longitude)
              .then(function (data) {
                var city = (data && data.city) || ''
                if (city) {
                  self.setData({ city: city, showCityPicker: false, locating: false })
                  store.setState({ city: city })
                  wx.showToast({ title: self.$t('toast.locatedTo', { city: city }), icon: 'none' })
                } else {
                  self.setData({ locating: false })
                  wx.showToast({ title: self.$t('toast.locateFailed'), icon: 'none' })
                }
              })
              .catch(function () {
                self.setData({ locating: false })
                wx.showToast({ title: self.$t('toast.locateFailed'), icon: 'none' })
              })
          },
          fail: function () {
            self.setData({ locating: false })
            wx.showToast({ title: self.$t('toast.locateFailedPerm'), icon: 'none' })
          }
        })
      },
      fail: function () {
        self.setData({ locating: false })
        wx.showToast({ title: self.$t('toast.needLocationPerm'), icon: 'none' })
      }
    })
  },

  onSelectCity: function (e) {
    var city = e.currentTarget.dataset.city
    this.setData({ city: city, showCityPicker: false })
    store.setState({ city: city })
    wx.showToast({ title: this.$t('toast.selectedCity', { city: city }), icon: 'none' })
  },

  onChangePhone: function () {
    router.navigate({ url: '/pages/profile/bind-phone/index' })
  },

  onSwitchRole: function () {
    var user = this.data.user
    if (!user) return
    var targetRole = user.role === 'patient' ? 'companion' : 'patient'
    var targetLabel = targetRole === 'patient' ? this.$t('role.patient') : this.$t('role.companion')
    var hasTargetRole = user.roles && user.roles.indexOf(targetRole) !== -1
    var self = this

    if (!hasTargetRole) {
      wx.showModal({
        title: self.$t('dialog.registerRoleTitle'),
        content: self.$t('dialog.registerRoleContent', { targetLabel: targetLabel }),
        confirmColor: '#1890FF',
        success: function (res) {
          if (res.confirm) {
            router.navigate({ url: '/pages/role-select/index?target=' + targetRole })
          }
        }
      })
      return
    }

    wx.showModal({
      title: self.$t('dialog.switchRoleTitle'),
      content: self.$t('dialog.switchRoleContent', { targetLabel: targetLabel }),
      confirmColor: '#1890FF',
      success: function (res) {
        if (res.confirm) {
          wx.showLoading({ title: self.$t('toast.switching') })
          switchRole(targetRole)
            .then(function (data) {
              wx.hideLoading()
              setAccessToken(data.access_token)
              setRefreshToken(data.refresh_token)
              store.setState({ user: data.user })
              var home = targetRole === 'patient' ? '/pages/patient/home/index' : '/pages/companion/home/index'
              router.relaunch({ url: home })
            })
            .catch(function () {
              wx.hideLoading()
              wx.showToast({ title: self.$t('toast.switchFailed'), icon: 'none' })
            })
        }
      }
    })
  },

  onClearCache: function () {
    var self = this
    wx.showModal({
      title: self.$t('dialog.tip'),
      content: self.$t('dialog.clearCacheConfirm'),
      success: function (res) {
        if (res.confirm) {
          wx.clearStorageSync()
          self.setData({ cacheSize: '0 KB' })
          wx.showToast({ title: self.$t('toast.cleared'), icon: 'success' })
        }
      }
    })
  },

  onAbout: function () {
    router.navigate({ url: '/pages/profile/about/index' })
  },

  onPrivacyPolicy: function () {
    router.navigate({ url: '/pages/legal/privacy/index' })
  },

  onUserAgreement: function () {
    router.navigate({ url: '/pages/legal/terms/index' })
  },

  onDeleteAccount: function () {
    router.navigate({ url: '/pages/settings/delete-account/index' })
  }
})
