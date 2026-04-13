const { switchRole } = require('../../../services/user')
const { setAccessToken, setRefreshToken } = require('../../../utils/token')
const { getHospitalFilters, getNearestRegion } = require('../../../services/hospital')
const store = require('../../../store/index')

Page({
  data: {
    cacheSize: '0 KB',
    user: null,
    city: '',
    showCityPicker: false,
    allCities: [],
    locating: false
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
                  wx.showToast({ title: '已定位到' + city, icon: 'none' })
                } else {
                  self.setData({ locating: false })
                  wx.showToast({ title: '定位失败', icon: 'none' })
                }
              })
              .catch(function () {
                self.setData({ locating: false })
                wx.showToast({ title: '定位失败', icon: 'none' })
              })
          },
          fail: function () {
            self.setData({ locating: false })
            wx.showToast({ title: '定位失败，请检查权限', icon: 'none' })
          }
        })
      },
      fail: function () {
        self.setData({ locating: false })
        wx.showToast({ title: '请允许位置权限', icon: 'none' })
      }
    })
  },

  onSelectCity: function (e) {
    var city = e.currentTarget.dataset.city
    this.setData({ city: city, showCityPicker: false })
    store.setState({ city: city })
    wx.showToast({ title: '已选择' + city, icon: 'none' })
  },

  onChangePhone: function () {
    wx.navigateTo({ url: '/pages/profile/bind-phone/index' })
  },

  onSwitchRole: function () {
    var user = this.data.user
    if (!user) return
    var targetRole = user.role === 'patient' ? 'companion' : 'patient'
    var targetLabel = targetRole === 'patient' ? '患者' : '陪诊师'
    var hasTargetRole = user.roles && user.roles.indexOf(targetRole) !== -1

    if (!hasTargetRole) {
      wx.showModal({
        title: '注册新角色',
        content: '您还没有' + targetLabel + '角色，是否前往注册？',
        confirmColor: '#1890FF',
        success: function (res) {
          if (res.confirm) {
            wx.navigateTo({ url: '/pages/role-select/index?target=' + targetRole })
          }
        }
      })
      return
    }

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
  },

  onDeleteAccount: function () {
    wx.navigateTo({ url: '/pages/settings/delete-account/index' })
  }
})
