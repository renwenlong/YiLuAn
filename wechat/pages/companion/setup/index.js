var { applyCompanion } = require('../../../services/companion')
var { getHospitals, getHospitalFilters, getNearestRegion } = require('../../../services/hospital')
var { sendOTP, bindPhone } = require('../../../services/auth')
var { isValidPhone, isValidOTP } = require('../../../utils/validate')
var { SERVICE_TYPES } = require('../../../utils/constants')
var store = require('../../../store/index')

Page({
  data: {
    realName: '',
    bio: '',
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

  onLoad() {
    var types = Object.keys(SERVICE_TYPES).map(function (key) {
      return { key: key, label: SERVICE_TYPES[key].label }
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
    self.setData({ city: '定位中...', locating: true })
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
                self._loadFilters()
                self._loadHospitals()
              })
              .catch(function () {
                self.setData({ city: '', locating: false })
                self._loadFilters()
                self._loadHospitals()
              })
          },
          fail: function () {
            self.setData({ city: '', locating: false })
            self._loadFilters()
            self._loadHospitals()
          }
        })
      },
      fail: function () {
        self.setData({ city: '', locating: false })
        self._loadFilters()
        self._loadHospitals()
      }
    })
  },

  _loadFilters() {
    var self = this
    var params = {}
    if (self.data.city && self.data.city !== '定位中...') params.city = self.data.city
    getHospitalFilters(params)
      .then(function (res) {
        var districts = ['不限'].concat(res.districts || [])
        var levels = ['不限'].concat(res.levels || [])
        var tags = ['不限'].concat(res.tags || [])
        self.setData({
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
    if (self.data.city && self.data.city !== '定位中...') params.city = self.data.city
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
      wx.showToast({ title: '请输入正确手机号', icon: 'none' })
      return
    }
    var self = this
    self.setData({ sendingOTP: true })
    sendOTP(self.data.phone)
      .then(function () {
        wx.showToast({ title: '验证码已发送', icon: 'success' })
        self._startCountdown()
      })
      .catch(function () {
        wx.showToast({ title: '发送失败', icon: 'none' })
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
      wx.showToast({ title: '请检查手机号和验证码', icon: 'none' })
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
        wx.showToast({ title: '手机号验证成功', icon: 'success' })
      })
      .catch(function () {
        self.setData({ bindingPhone: false })
        wx.showToast({ title: '验证失败，请重试', icon: 'none' })
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
  },

  onSubmit() {
    var d = this.data
    if (!d.realName.trim()) {
      wx.showToast({ title: '请输入真实姓名', icon: 'none' })
      return
    }
    if (!d.phoneBound) {
      wx.showToast({ title: '请先验证手机号', icon: 'none' })
      return
    }
    if (d.selectedServiceTypes.length === 0) {
      wx.showToast({ title: '请至少选择一种服务类型', icon: 'none' })
      return
    }

    this.setData({ saving: true })
    var self = this
    var body = {
      real_name: d.realName.trim(),
      service_types: d.selectedServiceTypes.join(','),
      bio: d.bio || undefined,
      service_hospitals: d.selectedHospitalIds.length > 0 ? d.selectedHospitalIds.join(',') : undefined
    }
    applyCompanion(body)
      .then(function (res) {
        self.setData({ saving: false })
        var state = store.getState()
        var user = Object.assign({}, state.user, res)
        store.setState({ user: user })
        wx.showToast({ title: '注册成功', icon: 'success' })
        setTimeout(function () {
          wx.reLaunch({ url: '/pages/companion/home/index' })
        }, 1500)
      })
      .catch(function (err) {
        self.setData({ saving: false })
        var msg = '注册失败'
        if (err && err.data && err.data.detail) msg = err.data.detail
        else if (err && err.message) msg = err.message
        wx.showToast({ title: msg, icon: 'none' })
      })
  }
})
