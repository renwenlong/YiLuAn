var createOrder = require('../../../services/order').createOrder
var getOrders = require('../../../services/order').getOrders
var searchHospitals = require('../../../services/hospital').searchHospitals
var getHospitalFilters = require('../../../services/hospital').getHospitalFilters
var getNearestRegion = require('../../../services/hospital').getNearestRegion
var getCompanionDetail = require('../../../services/companion').getCompanionDetail
var store = require('../../../store/index')
var SERVICE_TYPES = require('../../../utils/constants').SERVICE_TYPES

var DEFAULT_LEVEL = '三级甲等'

Page({
  data: {
    step: 1,
    startStep: 1,
    totalSteps: 4,
    stepLabels: [],
    serviceType: '',
    serviceTypeName: '',
    servicePrice: 0,
    hospital: '',
    hospitalName: '',
    date: '',
    time: '',
    notes: '',
    loading: false,
    hospitals: [],
    recentHospitals: [],
    // Cascading filter dropdowns
    filterProvinces: [],
    filterCities: [],
    filterDistricts: [],
    filterLevels: [],
    filterTags: [],
    selectedProvince: '',
    selectedCity: '',
    selectedDistrict: '',
    selectedLevel: DEFAULT_LEVEL,
    selectedTag: '',
    provinceIndex: 0,
    cityIndex: 0,
    districtIndex: 0,
    levelIndex: 0,
    tagIndex: 0,
    companionId: '',
    companionName: '',
    serviceTypesList: [],
    // Which content panel to show: 'service' | 'hospital' | 'datetime' | 'confirm'
    panel: 'service'
  },

  // Maps step → panel name
  _stepMap: null,

  _buildStepMap(hasType) {
    if (hasType) {
      this._stepMap = { 1: 'hospital', 2: 'datetime', 3: 'confirm' }
      return [
        { num: 1, label: '医院' },
        { num: 2, label: '日期' },
        { num: 3, label: '确认' }
      ]
    }
    this._stepMap = { 1: 'service', 2: 'hospital', 3: 'datetime', 4: 'confirm' }
    return [
      { num: 1, label: '服务' },
      { num: 2, label: '医院' },
      { num: 3, label: '日期' },
      { num: 4, label: '确认' }
    ]
  },

  onLoad(options) {
    var today = new Date()
    var year = today.getFullYear()
    var month = String(today.getMonth() + 1).padStart(2, '0')
    var day = String(today.getDate()).padStart(2, '0')
    var data = { date: year + '-' + month + '-' + day, time: '09:00' }

    var list = Object.keys(SERVICE_TYPES).map(function (key) {
      return { value: key, label: SERVICE_TYPES[key].label, price: SERVICE_TYPES[key].price }
    })
    data.serviceTypesList = list

    var hasType = !!(options.type && SERVICE_TYPES[options.type])

    if (hasType) {
      var info = SERVICE_TYPES[options.type]
      data.serviceType = options.type
      data.serviceTypeName = info.label
      data.servicePrice = info.price
      data.startStep = 1
      data.step = 1
      data.totalSteps = 3
      data.panel = 'hospital'
    } else {
      data.startStep = 1
      data.step = 1
      data.totalSteps = 4
      data.panel = 'service'
    }

    data.stepLabels = this._buildStepMap(hasType)
    this.setData(data)

    if (options.companion_id) {
      this.loadCompanion(options.companion_id)
    }

    this.loadRecentHospitals()
    this.initLocationAndFilters()
  },

  /**
   * 1. Load all filter options (provinces, levels, tags)
   * 2. Get user location → resolve to province/city
   * 3. Auto-set province/city + default level
   * 4. Auto-search hospitals
   */
  initLocationAndFilters() {
    var self = this
    // Load full filter options first
    getHospitalFilters({})
      .then(function (res) {
        var provinces = ['不限'].concat(res.provinces || [])
        var levels = ['不限'].concat(res.levels || [])
        var tags = ['不限'].concat(res.tags || [])

        // Find default level index
        var levelIdx = 0
        for (var i = 0; i < levels.length; i++) {
          if (levels[i] === DEFAULT_LEVEL) {
            levelIdx = i
            break
          }
        }

        self.setData({
          filterProvinces: provinces,
          filterLevels: levels,
          filterTags: tags,
          levelIndex: levelIdx,
          selectedLevel: levelIdx > 0 ? DEFAULT_LEVEL : ''
        })

        // Now try to get user location
        self.detectLocation(provinces)
      })
      .catch(function (err) {
        console.error('加载筛选项失败', err)
      })
  },

  detectLocation(provinces) {
    var self = this
    wx.getFuzzyLocation({
      type: 'wgs84',
      success: function (loc) {
        getNearestRegion(loc.latitude, loc.longitude)
          .then(function (region) {
            if (region && region.province) {
              self.applyRegion(region.province, region.city, provinces)
            } else {
              // No match — just do a search with default level
              self.doFilterSearch()
            }
          })
          .catch(function () {
            self.doFilterSearch()
          })
      },
      fail: function () {
        // Location denied or unavailable — show all hospitals with default level
        self.doFilterSearch()
      }
    })
  },

  /**
   * Auto-set province/city filters and cascade load cities/districts, then search.
   */
  applyRegion(province, city, provinces) {
    var self = this
    // Find province index
    provinces = provinces || self.data.filterProvinces
    var provIdx = 0
    for (var i = 0; i < provinces.length; i++) {
      if (provinces[i] === province) {
        provIdx = i
        break
      }
    }

    self.setData({
      provinceIndex: provIdx,
      selectedProvince: province
    })

    // Load cities for this province
    getHospitalFilters({ province: province })
      .then(function (res) {
        var cities = ['不限'].concat(res.cities || [])
        var districts = ['不限'].concat(res.districts || [])
        var data = {
          filterCities: cities,
          filterDistricts: districts,
          districtIndex: 0,
          selectedDistrict: ''
        }

        // Find city index
        if (city) {
          for (var i = 0; i < cities.length; i++) {
            if (cities[i] === city) {
              data.cityIndex = i
              data.selectedCity = city
              break
            }
          }
        }
        if (!data.selectedCity) {
          data.cityIndex = 0
          data.selectedCity = ''
        }

        self.setData(data)

        // If city was set, load districts for that city
        if (data.selectedCity) {
          getHospitalFilters({ province: province, city: data.selectedCity })
            .then(function (res2) {
              self.setData({
                filterDistricts: ['不限'].concat(res2.districts || [])
              })
              self.doFilterSearch()
            })
            .catch(function () {
              self.doFilterSearch()
            })
        } else {
          self.doFilterSearch()
        }
      })
      .catch(function () {
        self.doFilterSearch()
      })
  },

  loadFilters(province, city) {
    var self = this
    var params = {}
    if (province) params.province = province
    if (city) params.city = city
    getHospitalFilters(params)
      .then(function (res) {
        var data = {}
        if (!province && !city) {
          data.filterProvinces = ['不限'].concat(res.provinces || [])
          data.provinceIndex = 0
          data.selectedProvince = ''
        }
        if (!city) {
          data.filterCities = ['不限'].concat(res.cities || [])
          data.cityIndex = 0
          data.selectedCity = ''
        }
        data.filterDistricts = ['不限'].concat(res.districts || [])
        data.districtIndex = 0
        data.selectedDistrict = ''
        data.filterLevels = ['不限'].concat(res.levels || [])
        data.filterTags = ['不限'].concat(res.tags || [])
        self.setData(data)
      })
      .catch(function (err) {
        console.error('加载筛选项失败', err)
      })
  },

  loadRecentHospitals() {
    var self = this
    getOrders({ page: 1, page_size: 20 })
      .then(function (res) {
        var orders = res.items || res.data || []
        var seen = {}
        var hospitals = []
        for (var i = 0; i < orders.length; i++) {
          var o = orders[i]
          if (o.hospital_id && o.hospital_name && !seen[o.hospital_id]) {
            seen[o.hospital_id] = true
            hospitals.push({ id: o.hospital_id, name: o.hospital_name })
          }
        }
        if (hospitals.length > 0) {
          self.setData({
            recentHospitals: hospitals,
            hospital: hospitals[0].id,
            hospitalName: hospitals[0].name
          })
        }
      })
      .catch(function (err) {
        console.error('加载最近医院失败', err)
      })
  },

  loadCompanion(companionId) {
    var self = this
    getCompanionDetail(companionId)
      .then(function (res) {
        self.setData({
          companionId: res.id,
          companionName: res.real_name || ''
        })
      })
      .catch(function (err) {
        console.error('加载陪诊师信息失败', err)
      })
  },

  _updatePanel() {
    var panel = this._stepMap[this.data.step] || 'service'
    this.setData({ panel: panel })
  },

  onServiceTypeSelect(e) {
    var type = e.currentTarget.dataset.type
    var info = SERVICE_TYPES[type]
    this.setData({
      serviceType: type,
      serviceTypeName: info ? info.label : '',
      servicePrice: info ? info.price : 0
    })
  },

  nextStep() {
    var d = this.data
    var panel = d.panel

    if (panel === 'service' && !d.serviceType) {
      wx.showToast({ title: '请选择服务类型', icon: 'none' })
      return
    }
    if (panel === 'hospital' && !d.hospital) {
      wx.showToast({ title: '请选择医院', icon: 'none' })
      return
    }
    if (panel === 'datetime' && (!d.date || !d.time)) {
      wx.showToast({ title: '请选择日期和时间', icon: 'none' })
      return
    }

    if (d.step < d.totalSteps) {
      this.setData({ step: d.step + 1 })
      this._updatePanel()
    }
  },

  prevStep() {
    var d = this.data
    if (d.step > 1) {
      this.setData({ step: d.step - 1 })
      this._updatePanel()
    } else {
      wx.navigateBack()
    }
  },

  onDateChange(e) {
    this.setData({ date: e.detail.value })
  },

  onTimeChange(e) {
    this.setData({ time: e.detail.value })
  },

  onNotesInput(e) {
    this.setData({ notes: e.detail.value })
  },

  onProvinceChange(e) {
    var idx = Number(e.detail.value)
    var val = idx === 0 ? '' : this.data.filterProvinces[idx]
    this.setData({
      provinceIndex: idx,
      selectedProvince: val,
      cityIndex: 0,
      selectedCity: '',
      districtIndex: 0,
      selectedDistrict: ''
    })
    this.loadFilters(val)
    this.doFilterSearch()
  },

  onCityChange(e) {
    var idx = Number(e.detail.value)
    var val = idx === 0 ? '' : this.data.filterCities[idx]
    this.setData({
      cityIndex: idx,
      selectedCity: val,
      districtIndex: 0,
      selectedDistrict: ''
    })
    this.loadFilters(this.data.selectedProvince, val)
    this.doFilterSearch()
  },

  onDistrictChange(e) {
    var idx = Number(e.detail.value)
    var val = idx === 0 ? '' : this.data.filterDistricts[idx]
    this.setData({ districtIndex: idx, selectedDistrict: val })
    this.doFilterSearch()
  },

  onLevelChange(e) {
    var idx = Number(e.detail.value)
    var val = idx === 0 ? '' : this.data.filterLevels[idx]
    this.setData({ levelIndex: idx, selectedLevel: val })
    this.doFilterSearch()
  },

  onTagChange(e) {
    var idx = Number(e.detail.value)
    var val = idx === 0 ? '' : this.data.filterTags[idx]
    this.setData({ tagIndex: idx, selectedTag: val })
    this.doFilterSearch()
  },

  doFilterSearch() {
    var d = this.data
    var params = { page_size: 50 }
    if (d.selectedProvince) params.province = d.selectedProvince
    if (d.selectedCity) params.city = d.selectedCity
    if (d.selectedDistrict) params.district = d.selectedDistrict
    if (d.selectedLevel) params.level = d.selectedLevel
    if (d.selectedTag) params.tag = d.selectedTag
    this.setData({ loading: true })
    var self = this
    searchHospitals(params)
      .then(function (res) {
        var hospitals = res.items || res || []
        self.setData({ hospitals: hospitals, loading: false })
      })
      .catch(function () {
        wx.showToast({ title: '搜索失败', icon: 'none' })
        self.setData({ loading: false })
      })
  },

  onHospitalSelect(e) {
    var id = e.currentTarget.dataset.id
    var name = e.currentTarget.dataset.name
    this.setData({ hospital: id, hospitalName: name })
  },

  onSubmit() {
    var d = this.data
    if (d.loading) return
    this.setData({ loading: true })
    var orderData = {
      service_type: d.serviceType,
      hospital_id: d.hospital,
      appointment_date: d.date,
      appointment_time: d.time
    }
    if (d.notes) orderData.description = d.notes
    if (d.companionId) orderData.companion_id = d.companionId

    var self = this
    createOrder(orderData)
      .then(function (order) {
        self.setData({ loading: false })
        wx.showToast({ title: '订单创建成功', icon: 'success' })
        setTimeout(function () {
          wx.redirectTo({
            url: '/pages/patient/order-detail/index?id=' + order.id
          })
        }, 1500)
      })
      .catch(function (err) {
        self.setData({ loading: false })
        var msg = '创建失败'
        if (err && err.data && err.data.detail) msg = err.data.detail
        else if (err && err.message) msg = err.message
        wx.showToast({ title: msg, icon: 'none' })
      })
  }
})
