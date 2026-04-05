const { getPatientProfile, updatePatientProfile } = require('../../../services/user')
const { updateCompanionProfile, getMyProfile } = require('../../../services/companion')
const { getHospitals, getHospitalFilters } = require('../../../services/hospital')
const { SERVICE_TYPES } = require('../../../utils/constants')
const store = require('../../../store/index')

Page({
  data: {
    role: '',
    emergency_contact: '',
    emergency_phone: '',
    medical_notes: '',
    certifications: '',
    bio: '',
    service_area: '',
    // service types
    serviceTypeList: [],
    selectedServiceTypes: [],
    serviceTypeMap: {},
    // hospitals
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
    selectedDistricts: [],
    districtMap: {},
    serviceDistricts: [],
    city: '',
    loading: false,
    saving: false
  },

  _searchTimer: null,

  onLoad() {
    const state = store.getState()
    var role = (state && state.user && state.user.role) || 'patient'
    this.setData({ role: role })

    if (role === 'companion') {
      var types = Object.keys(SERVICE_TYPES).map(function (key) {
        return { key: key, label: SERVICE_TYPES[key].label }
      })
      this.setData({ serviceTypeList: types })
    }

    this.loadProfile()
  },

  loadProfile() {
    var role = this.data.role
    this.setData({ loading: true })

    if (role === 'patient') {
      getPatientProfile()
        .then((data) => {
          this.setData({
            emergency_contact: data.emergency_contact || '',
            emergency_phone: data.emergency_phone || '',
            medical_notes: data.medical_notes || '',
            loading: false
          })
        })
        .catch(() => {
          this.setData({ loading: false })
        })
    } else if (role === 'companion') {
      var state = store.getState()
      var city = (state && state.city) || '北京'
      getMyProfile()
        .then((profile) => {
          var hospitalIds = profile.service_hospitals ? profile.service_hospitals.split(',').filter(Boolean) : []
          var districts = profile.service_area ? profile.service_area.split('、').filter(Boolean) : []
          var serviceTypes = profile.service_types ? profile.service_types.split(',').filter(Boolean) : []
          var stMap = {}
          for (var i = 0; i < serviceTypes.length; i++) {
            stMap[serviceTypes[i]] = true
          }
          var hMap = {}
          for (var j = 0; j < hospitalIds.length; j++) {
            hMap[hospitalIds[j]] = true
          }
          var dMap = {}
          for (var k = 0; k < districts.length; k++) {
            dMap[districts[k]] = true
          }
          this.setData({
            certifications: profile.certifications || '',
            bio: profile.bio || '',
            service_area: profile.service_area || '',
            selectedHospitalIds: hospitalIds,
            hospitalIdMap: hMap,
            selectedDistricts: districts,
            districtMap: dMap,
            selectedServiceTypes: serviceTypes,
            serviceTypeMap: stMap,
            city: city,
            loading: false
          })
          this._loadFilters()
          this._loadHospitals()
        })
        .catch(() => {
          // Fallback to store data if API fails
          var user = ((state && state.user) || {})
          var hospitalIds = user.service_hospitals ? user.service_hospitals.split(',').filter(Boolean) : []
          var districts = user.service_area ? user.service_area.split('、').filter(Boolean) : []
          var serviceTypes = user.service_types ? user.service_types.split(',').filter(Boolean) : []
          var stMap = {}
          for (var i = 0; i < serviceTypes.length; i++) {
            stMap[serviceTypes[i]] = true
          }
          var hMap = {}
          for (var j = 0; j < hospitalIds.length; j++) {
            hMap[hospitalIds[j]] = true
          }
          var dMap = {}
          for (var k = 0; k < districts.length; k++) {
            dMap[districts[k]] = true
          }
          this.setData({
            certifications: user.certifications || '',
            bio: user.bio || '',
            service_area: user.service_area || '',
            selectedHospitalIds: hospitalIds,
            hospitalIdMap: hMap,
            selectedDistricts: districts,
            districtMap: dMap,
            selectedServiceTypes: serviceTypes,
            serviceTypeMap: stMap,
            city: city,
            loading: false
          })
          this._loadFilters()
          this._loadHospitals()
        })
    } else {
      this.setData({ loading: false })
    }
  },

  _loadFilters() {
    var self = this
    var params = {}
    if (self.data.city) params.city = self.data.city
    getHospitalFilters(params)
      .then(function (res) {
        var rawDistricts = res.districts || []
        var districts = ['不限'].concat(rawDistricts)
        var levels = ['不限'].concat(res.levels || [])
        var tags = ['不限'].concat(res.tags || [])
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

  onInputChange(e) {
    var field = e.currentTarget.dataset.field
    var obj = {}
    obj[field] = e.detail.value
    this.setData(obj)
  },

  _loadHospitals() {
    var self = this
    self.setData({ loadingHospitals: true })
    var params = { page_size: 100 }
    if (self.data.city) params.city = self.data.city
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
    this.setData({ selectedDistricts: list, districtMap: map, service_area: list.join('、') })
  },

  onSave() {
    var role = this.data.role
    this.setData({ saving: true })

    if (role === 'patient') {
      var patientData = {
        emergency_contact: this.data.emergency_contact,
        emergency_phone: this.data.emergency_phone,
        medical_notes: this.data.medical_notes
      }
      updatePatientProfile(patientData)
        .then(() => {
          this.setData({ saving: false })
          wx.showToast({ title: '保存成功', icon: 'success' })
          setTimeout(function() {
            wx.navigateBack()
          }, 1500)
        })
        .catch(() => {
          this.setData({ saving: false })
          wx.showToast({ title: '保存失败', icon: 'none' })
        })
    } else if (role === 'companion') {
      if (this.data.selectedServiceTypes.length === 0) {
        this.setData({ saving: false })
        wx.showToast({ title: '请至少选择一种服务类型', icon: 'none' })
        return
      }
      var companionData = {
        certifications: this.data.certifications,
        bio: this.data.bio,
        service_area: this.data.selectedDistricts.join('、'),
        service_types: this.data.selectedServiceTypes.join(','),
        service_hospitals: this.data.selectedHospitalIds.join(',')
      }
      updateCompanionProfile(companionData)
        .then((data) => {
          this.setData({ saving: false })
          var state = store.getState()
          // Only merge companion-specific fields into user, avoid overwriting user.id
          var companionFields = {
            certifications: data.certifications,
            bio: data.bio,
            service_area: data.service_area,
            service_types: data.service_types,
            service_hospitals: data.service_hospitals,
            service_city: data.service_city
          }
          var user = Object.assign({}, state.user, companionFields)
          store.setState({ user: user })
          wx.showToast({ title: '保存成功', icon: 'success' })
          setTimeout(function() {
            wx.navigateBack()
          }, 1500)
        })
        .catch((err) => {
          this.setData({ saving: false })
          var msg = '保存失败'
          if (err && err.data && err.data.detail) {
            msg = typeof err.data.detail === 'string' ? err.data.detail : '保存失败，请重试'
          }
          wx.showToast({ title: msg, icon: 'none' })
        })
    }
  }
})
