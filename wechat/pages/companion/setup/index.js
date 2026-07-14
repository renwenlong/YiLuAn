var { applyCompanion } = require('../../../services/companion')
var { getHospitals, getHospitalFilters, getNearestRegion } = require('../../../services/hospital')
var { sendOTP, bindPhone } = require('../../../services/auth')
var { isValidPhone, isValidOTP } = require('../../../utils/validate')
var { SERVICE_TYPES } = require('../../../utils/constants')
var store = require('../../../store/index')
const router = require('../../../utils/router')
const i18nBehavior = require('../../../behaviors/i18n')
const i18n = require('../../../utils/i18n')

Page({
  behaviors: [i18nBehavior],
  data: {
    i18nScopes: ['common', 'companionSetup', 'serviceType'],
    // 动态串 (behavior 注入 t 后由 _refreshDynamicText 计算)
    cityWrap: '',
    selectedHospitalCountText: '',
    realName: '',
    bio: '',
    certifications: '',
    // phone
    phone: '',
    phoneBound: false,
    code: '',
    countdown: 0,
    sendingOTP: false,
    bindingPhone: false,
    // service types
    serviceTypeList: [],
    selectedServiceTypes: [],
    serviceTypeMap: {},
    // service area (districts)
    selectedDistricts: [],
    districtMap: {},
    serviceDistricts: [],
    // hospital
    city: '',
    locating: false,
    allHospitals: [],
    selectedHospitalIds: [],
    hospitalIdMap: {},
    hospitalKeyword: '',
    // hospital filters (picker-based)
    allDistricts: [],
    allLevels: [],
    allTags: [],
    districtIndex: 0,
    levelIndex: 0,
    tagIndex: 0,
    filterDistrict: '',
    filterLevel: '',
    filterTag: '',
    loadingHospitals: false,
    saving: false
  },

  _searchTimer: null,

  // 计算依赖 city / 选中数量的动态 UI 串 (city 非'定位中'占位时才拼括号)
  _refreshDynamicText() {
    var city = this.data.city
    var showCity = city && !this.data.locating
    this.setData({
      cityWrap: showCity ? i18n.t('companionSetup.cityWrap', { city: city }) : '',
      selectedHospitalCountText: this.data.selectedHospitalIds.length > 0
        ? i18n.t('companionSetup.selectedHospitalCount', { count: this.data.selectedHospitalIds.length })
        : ''
    })
  },

  onLoad() {
    var types = Object.keys(SERVICE_TYPES).map(function (key) {
      var label = i18n.t('serviceType.' + key)
      return { key: key, label: label === 'serviceType.' + key ? SERVICE_TYPES[key].label : label }
    })
    var state = store.getState()
    var user = (state && state.user) || {}
    this.setData({
      serviceTypeList: types,
      phone: user.phone || '',
      phoneBound: !!user.phone
    })
    this._autoLocate()
  },

  _autoLocate() {
    var self = this
    self.setData({ city: '', locating: true })
    self._refreshDynamicText()
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
                  self.setData({ city: city, locating: false })
                  store.setState({ city: city })
                } else {
                  self.setData({ city: '', locating: false })
                }
                self._refreshDynamicText()
                self._loadFilters()
                self._loadHospitals()
              })
              .catch(function () {
                self.setData({ city: '', locating: false })
                self._refreshDynamicText()
                self._loadFilters()
                self._loadHospitals()
              })
          },
          fail: function () {
            self.setData({ city: '', locating: false })
            self._refreshDynamicText()
            self._loadFilters()
            self._loadHospitals()
          }
        })
      },
      fail: function () {
        self.setData({ city: '', locating: false })
        self._refreshDynamicText()
        self._loadFilters()
        self._loadHospitals()
      }
    })
  },

  _loadFilters() {
    var self = this
    var params = {}
    if (self.data.city && !self.data.locating) params.city = self.data.city
    getHospitalFilters(params)
      .then(function (res) {
        var rawDistricts = res.districts || []
        var districts = [i18n.t('companionSetup.filterDistrict')].concat(rawDistricts)
        var levels = [i18n.t('companionSetup.filterLevel')].concat(res.levels || [])
        var tags = [i18n.t('companionSetup.filterTag')].concat(res.tags || [])
        self.setData({
          serviceDistricts: rawDistricts,
          allDistricts: districts,
          allLevels: levels,
          allTags: tags,
          districtIndex: 0,
          levelIndex: 0,
          tagIndex: 0
        })
      })
      .catch(function () {
        self.setData({ allDistricts: [], allLevels: [], allTags: [] })
      })
  },

  _loadHospitals() {
    var self = this
    self.setData({ loadingHospitals: true })
    var params = { page_size: 100 }
    if (self.data.city && !self.data.locating) params.city = self.data.city
    if (self.data.hospitalKeyword) params.keyword = self.data.hospitalKeyword
    if (self.data.filterDistrict) params.district = self.data.filterDistrict
    if (self.data.filterLevel) params.level = self.data.filterLevel
    if (self.data.filterTag) params.tag = self.data.filterTag
    getHospitals(params)
      .then(function (res) {
        var items = res.items || res.data || (Array.isArray(res) ? res : [])
        var list = items.map(function (h) {
          return { id: h.id, name: h.name, level: h.level || '', district: h.district || '' }
        })
        self.setData({ allHospitals: list, loadingHospitals: false })
      })
      .catch(function () {
        self.setData({ allHospitals: [], loadingHospitals: false })
      })
  },

  onInputChange(e) {
    var field = e.currentTarget.dataset.field
    var obj = {}
    obj[field] = e.detail.value
    this.setData(obj)
  },

  // Phone + OTP
  onPhoneInput(e) {
    this.setData({ phone: e.detail.value })
  },

  onCodeInput(e) {
    this.setData({ code: e.detail.value })
  },

  onSendOTP() {
    if (!isValidPhone(this.data.phone)) {
      wx.showToast({ title: i18n.t('companionSetup.toastPhoneInvalid'), icon: 'none' })
      return
    }
    var self = this
    self.setData({ sendingOTP: true })
    sendOTP(self.data.phone)
      .then(function () {
        wx.showToast({ title: i18n.t('companionSetup.toastCodeSent'), icon: 'success' })
        self._startCountdown()
      })
      .catch(function () {
        wx.showToast({ title: i18n.t('companionSetup.toastSendFailed'), icon: 'none' })
      })
      .finally(function () {
        self.setData({ sendingOTP: false })
      })
  },

  _startCountdown() {
    var self = this
    self.setData({ countdown: 60 })
    var timer = setInterval(function () {
      if (self.data.countdown <= 1) {
        clearInterval(timer)
        self.setData({ countdown: 0 })
        return
      }
      self.setData({ countdown: self.data.countdown - 1 })
    }, 1000)
  },

  onBindPhone() {
    if (!isValidPhone(this.data.phone) || !isValidOTP(this.data.code)) {
      wx.showToast({ title: i18n.t('companionSetup.toastCheckPhoneCode'), icon: 'none' })
      return
    }
    var self = this
    self.setData({ bindingPhone: true })
    bindPhone(self.data.phone, self.data.code)
      .then(function () {
        var state = store.getState()
        var user = Object.assign({}, state.user, { phone: self.data.phone })
        store.setState({ user: user })
        self.setData({ phoneBound: true, bindingPhone: false })
        wx.showToast({ title: i18n.t('companionSetup.toastPhoneVerified'), icon: 'success' })
      })
      .catch(function () {
        self.setData({ bindingPhone: false })
        wx.showToast({ title: i18n.t('companionSetup.toastVerifyFailedRetry'), icon: 'none' })
      })
  },

  onServiceTypeToggle(e) {
    var key = e.currentTarget.dataset.key
    var list = this.data.selectedServiceTypes.slice()
    var map = {}
    var idx = list.indexOf(key)
    if (idx >= 0) {
      list.splice(idx, 1)
    } else {
      list.push(key)
    }
    for (var i = 0; i < list.length; i++) {
      map[list[i]] = true
    }
    this.setData({ selectedServiceTypes: list, serviceTypeMap: map })
  },

  onDistrictToggle(e) {
    var name = e.currentTarget.dataset.name
    var list = this.data.selectedDistricts.slice()
    var map = {}
    var idx = list.indexOf(name)
    if (idx >= 0) {
      list.splice(idx, 1)
    } else {
      list.push(name)
    }
    for (var i = 0; i < list.length; i++) {
      map[list[i]] = true
    }
    this.setData({ selectedDistricts: list, districtMap: map })
  },

  onHospitalSearch(e) {
    var self = this
    self.setData({ hospitalKeyword: e.detail.value })
    if (self._searchTimer) clearTimeout(self._searchTimer)
    self._searchTimer = setTimeout(function () {
      self._loadHospitals()
    }, 300)
  },

  onFilterDistrictChange(e) {
    var idx = Number(e.detail.value)
    var val = idx === 0 ? '' : this.data.allDistricts[idx]
    this.setData({ districtIndex: idx, filterDistrict: val })
    this._loadHospitals()
  },

  onFilterLevelChange(e) {
    var idx = Number(e.detail.value)
    var val = idx === 0 ? '' : this.data.allLevels[idx]
    this.setData({ levelIndex: idx, filterLevel: val })
    this._loadHospitals()
  },

  onFilterTagChange(e) {
    var idx = Number(e.detail.value)
    var val = idx === 0 ? '' : this.data.allTags[idx]
    this.setData({ tagIndex: idx, filterTag: val })
    this._loadHospitals()
  },

  onHospitalToggle(e) {
    var id = e.currentTarget.dataset.id
    var ids = this.data.selectedHospitalIds.slice()
    var map = {}
    var idx = ids.indexOf(id)
    if (idx >= 0) {
      ids.splice(idx, 1)
    } else {
      ids.push(id)
    }
    for (var i = 0; i < ids.length; i++) {
      map[ids[i]] = true
    }
    this.setData({ selectedHospitalIds: ids, hospitalIdMap: map })
    this._refreshDynamicText()
  },

  onSubmit() {
    var d = this.data
    if (!d.realName.trim()) {
      wx.showToast({ title: i18n.t('companionSetup.toastNeedRealName'), icon: 'none' })
      return
    }
    if (!d.phoneBound) {
      wx.showToast({ title: i18n.t('companionSetup.toastNeedPhone'), icon: 'none' })
      return
    }
    if (d.selectedServiceTypes.length === 0) {
      wx.showToast({ title: i18n.t('companionSetup.toastNeedServiceType'), icon: 'none' })
      return
    }

    this.setData({ saving: true })
    var self = this
    var body = {
      real_name: d.realName.trim(),
      service_types: d.selectedServiceTypes.join(','),
      bio: d.bio || undefined,
      certifications: d.certifications || undefined,
      service_area: d.selectedDistricts.length > 0 ? d.selectedDistricts.join('、') : undefined,
      service_city: d.city && !d.locating ? d.city : undefined,
      service_hospitals: d.selectedHospitalIds.length > 0 ? d.selectedHospitalIds.join(',') : undefined
    }
    applyCompanion(body)
      .then(function (res) {
        self.setData({ saving: false })
        var state = store.getState()
        var user = Object.assign({}, state.user, res)
        store.setState({ user: user })
        wx.showToast({ title: i18n.t('companionSetup.toastRegisterSuccess'), icon: 'success' })
        setTimeout(function () {
          router.relaunch({ url: '/pages/companion/home/index' })
        }, 1500)
      })
      .catch(function (err) {
        self.setData({ saving: false })
        var msg = i18n.t('companionSetup.toastRegisterFailed')
        if (err && err.data && err.data.detail) msg = err.data.detail
        else if (err && err.message) msg = err.message
        wx.showToast({ title: msg, icon: 'none' })
      })
  }
})
