const { getCompanionDetail, getCompanionReviews } = require('../../services/companion')
const store = require('../../store/index')

Page({
  data: {
    companion: null,
    reviews: [],
    loading: true
  },

  onLoad(options) {
    this.companionId = options.id
    this.loadData()
  },

  async loadData() {
    this.setData({ loading: true })
    try {
      const [rawCompanion, reviewsRes] = await Promise.all([
        getCompanionDetail(this.companionId),
        getCompanionReviews(this.companionId)
      ])
      var companion = {
        id: rawCompanion.id,
        name: rawCompanion.name || rawCompanion.user_name || '',
        avatar: rawCompanion.avatar || rawCompanion.user_avatar || '',
        bio: rawCompanion.bio || '',
        rating: rawCompanion.avg_rating || rawCompanion.rating || 0,
        completedOrders: rawCompanion.total_orders || rawCompanion.completedOrders || 0,
        serviceArea: rawCompanion.service_area || rawCompanion.serviceArea || '',
        experience: rawCompanion.experience || '',
        serviceAreas: rawCompanion.service_areas || rawCompanion.serviceAreas || [],
        is_verified: rawCompanion.is_verified || false
      }
      this.setData({
        companion: companion,
        reviews: reviewsRes.list || reviewsRes || []
      })
    } catch (err) {
      wx.showToast({ title: '加载失败', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  onBook() {
    wx.navigateTo({
      url: '/pages/patient/create-order/index?companionId=' + this.companionId
    })
  },

  onPreviewAvatar() {
    const { companion } = this.data
    if (companion && companion.avatar) {
      wx.previewImage({
        urls: [companion.avatar],
        current: companion.avatar
      })
    }
  }
})
