const { getCompanions } = require('../../../services/companion')
const analytics = require('../../../utils/analytics')
const { getOrders } = require('../../../services/order')
const { getHospitals, getHospitalFilters, getNearestRegion } = require('../../../services/hospital')
const { SERVICE_TYPES } = require('../../../utils/constants')
const store = require('../../../store/index')
const router = require('../../../utils/router')
const logger = require('../../../utils/logger')
const i18n = require('../../../utils/i18n')
const i18nBehavior = require('../../../behaviors/i18n')

// 内部城市哨兵（不直接显示，显示走 cityDisplay + i18n）
var CITY_LOCATING = '__LOCATING__'
var CITY_UNSET = '__UNSET__'

Page({
  behaviors: [i18nBehavior],
  data: {
    i18nScopes: ['common', 'home', 'city', 'toast'],
    city: '',
    cityDisplay: '',
    hospitals: [],
    hospitalKeyword: '',
    companions: [],
    serviceTypes: [],
    selectedService: '',
    selectedHospital: null,
    loadingCompanions: false,
    loadingMore: false,
    hasMore: true,
    showCityPicker: false,
    allCities: [],
    locating: false,
    matchedTitle: ''
  },

  // 城市显示同步：哨兵→i18n，真城市名→原值
  _syncCityDisplay: function () {
    var c = this.data.city
    var disp = c
    if (c === CITY_LOCATING) {
      disp = i18n.t('city.locating')
    } else if (c === CITY_UNSET || !c) {
      disp = i18n.t('common.notSet')
    }
    if (disp !== this.data.cityDisplay) {
      this.setData({ cityDisplay: disp })
    }
  },

  // 匹配标题同步（含医院名占位）
  _syncMatchedTitle: function () {
    var h = this.data.selectedHospital
    if (h && h.name) {
      this.setData({ matchedTitle: i18n.t('home.matchedAt', { name: h.name }) })
    }
  },

  _page: 1,
  _usedCompanionIds: [],
  _shownIds: {},
  _searchTimer: null,

  onLoad() {
    var self = this
    // [funnel-1] 浏览陪诊列表 — 进入首页即认为漏斗起点
    try { analytics.trackFunnel(analytics.FUNNEL_STEPS.COMPANION_LIST_VIEW, { source: 'home_onLoad' }) } catch (_) {}
    var types = Object.keys(SERVICE_TYPES).map(function (key) {
      return {
        key: key,
        name: SERVICE_TYPES[key].label,
        price: SERVICE_TYPES[key].price,
        icon: SERVICE_TYPES[key].icon || ''
      }
    })
    this.setData({ serviceTypes: types })

    // Pre-load used companions (no city dependency)
    this._loadUsedCompanions()

    // Try store city first, otherwise auto-locate
    // Both paths end by calling _onCityReady which loads hospitals + companions together
    var state = store.getState()
    if (state && state.city) {
      this.setData({ city: state.city })
      this._syncCityDisplay()
      this._onCityReady()
    } else {
      this._autoLocate()
    }
  },

  onShow() {
    // 语言可能在其他页切换，回首页重算 js 现算的显示串
    this._syncCityDisplay()
    this._syncMatchedTitle()
    var state = store.getState()
    if (state && state.city && state.city !== this.data.city) {
      this.setData({ city: state.city })
      this._syncCityDisplay()
      this._fetchHospitals()
      this.fetchCompanions()
    }
  },

  _onCityReady() {
    this._fetchHospitals()
    this.fetchCompanions()
  },

  _autoLocate() {
    var self = this
    self.setData({ city: CITY_LOCATING, locating: true })
    self._syncCityDisplay()
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
                  self.setData({ city: CITY_UNSET, locating: false })
                }
                self._syncCityDisplay()
                self._onCityReady()
              })
              .catch(function () {
                self.setData({ city: CITY_UNSET, locating: false })
                self._syncCityDisplay()
                self._onCityReady()
              })
          },
          fail: function () {
            self.setData({ city: CITY_UNSET, locating: false })
            self._syncCityDisplay()
            self._onCityReady()
          }
        })
      },
      fail: function () {
        self.setData({ city: CITY_UNSET, locating: false })
        self._syncCityDisplay()
        self._onCityReady()
      }
    })
  },

  _fetchHospitals() {
    var self = this
    var params = { page_size: 3 }
    var validCity = self.data.city && self.data.city !== CITY_UNSET && self.data.city !== CITY_LOCATING
    if (this.data.hospitalKeyword) {
      params.keyword = this.data.hospitalKeyword
      if (validCity) {
        params.city = this.data.city
      }
    } else if (validCity) {
      params.city = this.data.city
    }
    getHospitals(params)
      .then(function (res) {
        var items = res.items || res.data || (Array.isArray(res) ? res : [])
        var list = items.map(function (h) {
          return {
            id: h.id,
            name: h.name,
            level: h.level || '',
            district: h.district || '',
            city: h.city || ''
          }
        })
        self.setData({ hospitals: list })
        // When location failed, infer city from hospital results to keep companions in sync
        if (!validCity && list.length > 0 && list[0].city) {
          var inferredCity = list[0].city
          self.setData({ city: inferredCity })
          store.setState({ city: inferredCity })
          self._syncCityDisplay()
          self.fetchCompanions()
        }
      })
      .catch(function () {
        self.setData({ hospitals: [] })
      })
  },

  onHospitalSearch(e) {
    var self = this
    this.setData({ hospitalKeyword: e.detail.value })
    if (this._searchTimer) clearTimeout(this._searchTimer)
    this._searchTimer = setTimeout(function () {
      self._fetchHospitals()
    }, 300)
  },

  onHospitalTap(e) {
    var ds = e.currentTarget.dataset
    var current = this.data.selectedHospital
    if (current && current.id === ds.id) {
      this.setData({ selectedHospital: null })
    } else {
      this.setData({ selectedHospital: { id: ds.id, name: ds.name } })
    }
    this._syncMatchedTitle()
    this.fetchCompanions(this.data.selectedService)
  },

  onClearHospital() {
    this.setData({ selectedHospital: null, selectedService: '' })
    this.fetchCompanions()
  },

  onCityTap() {
    if (this.data.city === CITY_LOCATING) return
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

  onCloseCityPicker() {
    this.setData({ showCityPicker: false })
  },

  onAutoLocate() {
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
                  self._syncCityDisplay()
                  self._fetchHospitals()
                  self.fetchCompanions()
                  wx.showToast({ title: i18n.t('toast.locatedTo', { city: city }), icon: 'none' })
                } else {
                  self.setData({ locating: false })
                  wx.showToast({ title: i18n.t('toast.locateFailed'), icon: 'none' })
                }
              })
              .catch(function () {
                self.setData({ locating: false })
                wx.showToast({ title: i18n.t('toast.locateFailed'), icon: 'none' })
              })
          },
          fail: function () {
            self.setData({ locating: false })
            wx.showToast({ title: i18n.t('toast.locateFailedPerm'), icon: 'none' })
          }
        })
      },
      fail: function () {
        self.setData({ locating: false })
        wx.showToast({ title: i18n.t('toast.needLocationPerm'), icon: 'none' })
      }
    })
  },

  onSelectCity(e) {
    var city = e.currentTarget.dataset.city
    this.setData({ city: city, showCityPicker: false, selectedHospital: null })
    store.setState({ city: city })
    this._syncCityDisplay()
    this._fetchHospitals()
    this.fetchCompanions()
    wx.showToast({ title: i18n.t('toast.selectedCity', { city: city }), icon: 'none' })
  },

  _loadUsedCompanions() {
    var self = this
    return getOrders({ page: 1, page_size: 100 })
      .then(function (res) {
        var orders = res.items || res.data || (Array.isArray(res) ? res : [])
        var seen = {}
        var ids = []
        orders.forEach(function (o) {
          if (o.companion_id && !seen[o.companion_id]) {
            seen[o.companion_id] = true
            ids.push(o.companion_id)
          }
        })
        self._usedCompanionIds = ids
      })
      .catch(function () {
        self._usedCompanionIds = []
      })
  },

  _sortByUsed(list) {
    var usedSet = {}
    this._usedCompanionIds.forEach(function (id) { usedSet[id] = true })
    var used = []
    var rest = []
    list.forEach(function (item) {
      if (usedSet[item.id]) {
        used.push(item)
      } else {
        rest.push(item)
      }
    })
    return used.concat(rest)
  },

  onServiceTap(e) {
    var type = e.currentTarget.dataset.type
    var selected = this.data.selectedService === type ? '' : type
    this.setData({ selectedService: selected })
    this.fetchCompanions(selected)
  },

  _mapCompanions(res) {
    var raw = Array.isArray(res) ? res : (res.items || res.data || [])
    return raw.map(function (item) {
      return {
        id: item.id,
        name: item.real_name || item.display_name || '',
        rating: item.avg_rating ? parseFloat(item.avg_rating.toFixed(1)) : 0,
        completed_orders: item.total_orders || 0,
        service_areas: item.service_area ? item.service_area.split('、') : []
      }
    })
  },

  _dedup(list) {
    var self = this
    var result = []
    list.forEach(function (item) {
      if (!self._shownIds[item.id]) {
        self._shownIds[item.id] = true
        result.push(item)
      }
    })
    return result
  },

  fetchCompanions(serviceType) {
    this._page = 1
    this._shownIds = {}
    this.setData({ companions: [], loadingCompanions: true, hasMore: true })
    this._loadPage(serviceType, false)
  },

  onLoadMore() {
    if (this.data.loadingMore || !this.data.hasMore) return
    this._loadPage(this.data.selectedService, true)
  },

  _loadPage(serviceType, append) {
    var self = this
    var pageSize = serviceType ? 6 : 3
    if (append) {
      this.setData({ loadingMore: true })
    }

    var page = append ? this._page + 1 : 1
    var params = { page: page, page_size: pageSize }
    var validCity = self.data.city && self.data.city !== CITY_UNSET && self.data.city !== CITY_LOCATING
    if (validCity) {
      params.city = self.data.city
    }
    if (serviceType) {
      params.service_type = serviceType
    }
    if (self.data.selectedHospital) {
      params.hospital_id = self.data.selectedHospital.id
    }

    getCompanions(params)
      .then(function (res) {
        var list = self._dedup(self._mapCompanions(res))
        self._page = page
        var companions = append ? self.data.companions.concat(list) : self._sortByUsed(list)
        self.setData({
          companions: companions,
          loadingCompanions: false,
          loadingMore: false,
          hasMore: list.length >= pageSize
        })
      })
      .catch(function (err) {
        logger.error('获取陪诊师失败', { err: err && (err.message || String(err)) })
        self.setData({ loadingCompanions: false, loadingMore: false })
      })
  },

  onCompanionTap(e) {
    var id = e.detail.id || e.currentTarget.dataset.id
    router.navigate({
      url: '/pages/companion-detail/index?id=' + id
    })
  },

  onBookCompanion(e) {
    var id = e.detail.id || e.currentTarget.dataset.id
    var hospital = this.data.selectedHospital
    var type = this.data.selectedService
    if (!hospital) {
      wx.showToast({ title: i18n.t('toast.selectHospitalFirst'), icon: 'none' })
      return
    }
    if (!type) {
      wx.showToast({ title: i18n.t('toast.selectServiceFirst'), icon: 'none' })
      return
    }
    if (!id) {
      wx.showToast({ title: i18n.t('toast.selectCompanionFirst'), icon: 'none' })
      return
    }
    router.navigate({
      url: '/pages/patient/create-order/index?type=' + type + '&companion_id=' + id + '&hospital_id=' + hospital.id + '&hospital_name=' + encodeURIComponent(hospital.name)
    })
  },

  onPullDownRefresh() {
    this.fetchCompanions(this.data.selectedService)
    wx.stopPullDownRefresh()
  }
})
