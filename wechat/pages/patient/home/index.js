const { getCompanions } = require('../../../services/companion')
const { SERVICE_TYPES } = require('../../../utils/constants')
const store = require('../../../store/index')

Page({
  data: {
    companions: [],
    serviceTypes: []
  },

  onLoad() {
    const types = Object.keys(SERVICE_TYPES).map(key => ({
      key: key,
      name: SERVICE_TYPES[key].label,
      icon: SERVICE_TYPES[key].icon || ''
    }))
    this.setData({ serviceTypes: types })
    this.fetchCompanions()
  },

  fetchCompanions() {
    getCompanions({ page: 1, page_size: 5 })
      .then(res => {
        const raw = Array.isArray(res) ? res : (res.items || res.data || [])
        const list = raw.map(item => ({
          id: item.id,
          name: item.real_name || item.display_name || '',
          rating: item.avg_rating || 0,
          completed_orders: item.total_orders || 0,
          service_areas: item.service_area ? item.service_area.split('、') : []
        }))
        this.setData({ companions: list })
      })
      .catch(err => {
        console.error('获取推荐陪诊师失败', err)
      })
  },

  onServiceTap(e) {
    const type = e.currentTarget.dataset.type
    wx.navigateTo({
      url: '/pages/patient/create-order/index?type=' + type
    })
  },

  onCompanionTap(e) {
    const id = e.currentTarget.dataset.id
    wx.navigateTo({
      url: '/pages/companion-detail/index?id=' + id
    })
  },

  onPullDownRefresh() {
    this.fetchCompanions()
    wx.stopPullDownRefresh()
  }
})
