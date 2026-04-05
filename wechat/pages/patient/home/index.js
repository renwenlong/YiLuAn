const { getCompanions } = require('../../../services/companion')
const { SERVICE_TYPES } = require('../../../utils/constants')
const store = require('../../../store/index')

Page({
  data: {
    companions: [],
    serviceTypes: [],
    selectedService: '',
    loadingCompanions: false
  },

  onLoad() {
    var types = Object.keys(SERVICE_TYPES).map(function (key) {
      return {
        key: key,
        name: SERVICE_TYPES[key].label,
        price: SERVICE_TYPES[key].price,
        icon: SERVICE_TYPES[key].icon || ''
      }
    })
    this.setData({ serviceTypes: types })
    this.fetchCompanions()
  },

  onServiceTap(e) {
    var type = e.currentTarget.dataset.type
    var selected = this.data.selectedService === type ? '' : type
    this.setData({
      selectedService: selected
    })
    this.fetchCompanions(selected)
  },

  fetchCompanions(serviceType) {
    var params = { page: 1, page_size: 10 }
    if (serviceType) {
      params.service_type = serviceType
    }
    this.setData({ loadingCompanions: true })
    var self = this
    getCompanions(params)
      .then(function (res) {
        var raw = Array.isArray(res) ? res : (res.items || res.data || [])
        var list = raw.map(function (item) {
          return {
            id: item.id,
            name: item.real_name || item.display_name || '',
            rating: item.avg_rating || 0,
            completed_orders: item.total_orders || 0,
            service_areas: item.service_area ? item.service_area.split('、') : []
          }
        })
        self.setData({ companions: list, loadingCompanions: false })
      })
      .catch(function (err) {
        console.error('获取推荐陪诊师失败', err)
        self.setData({ loadingCompanions: false })
      })
  },

  onCompanionTap(e) {
    var id = e.detail.id || e.currentTarget.dataset.id
    wx.navigateTo({
      url: '/pages/companion-detail/index?id=' + id
    })
  },

  onBookCompanion(e) {
    var id = e.detail.id || e.currentTarget.dataset.id
    var type = this.data.selectedService
    if (!type) {
      wx.showToast({ title: '请先选择服务类型', icon: 'none' })
      return
    }
    wx.navigateTo({
      url: '/pages/patient/create-order/index?type=' + type + '&companion_id=' + id
    })
  },

  onQuickOrder() {
    var type = this.data.selectedService
    if (!type) {
      wx.showToast({ title: '请先选择服务类型', icon: 'none' })
      return
    }
    wx.navigateTo({
      url: '/pages/patient/create-order/index?type=' + type
    })
  },

  onPullDownRefresh() {
    this.fetchCompanions(this.data.selectedService)
    wx.stopPullDownRefresh()
  }
})
