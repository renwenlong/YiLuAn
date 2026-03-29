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
      const [companion, reviewsRes] = await Promise.all([
        getCompanionDetail(this.companionId),
        getCompanionReviews(this.companionId)
      ])
      this.setData({
        companion,
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
      url: `/pages/patient/create-order/index?companionId=${this.companionId}`
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
