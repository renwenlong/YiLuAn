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
        name: rawCompanion.real_name || rawCompanion.display_name || '',
        avatar: rawCompanion.avatar || '',
        bio: rawCompanion.bio || '',
        rating: rawCompanion.avg_rating ? parseFloat(rawCompanion.avg_rating.toFixed(1)) : 0,
        completedOrders: rawCompanion.total_orders || 0,
        serviceArea: rawCompanion.service_area || '',
        experience: rawCompanion.experience || '',
        serviceAreas: rawCompanion.service_area ? rawCompanion.service_area.split('、') : [],
        is_verified: rawCompanion.verification_status === 'verified',
        // F-01: certification display
        certificationType: rawCompanion.certification_type || '',
        certificationNo: rawCompanion.certification_no || '',
        certificationImageUrl: rawCompanion.certification_image_url || '',
        certifiedAt: rawCompanion.certified_at || '',
        hasCertification: !!(rawCompanion.certification_image_url && rawCompanion.certification_type),
        // F-04: 4-dimension average ratings (server-computed)
        dimensionScores: rawCompanion.dimension_scores || {
          punctuality: 0, professionalism: 0, communication: 0, attitude: 0
        }
      }
      var rawReviews = (reviewsRes && reviewsRes.items) || []
      var reviews = rawReviews.map(function (r) {
        return {
          id: r.id,
          rating: r.rating,
          content: r.content,
          userName: r.patient_name || '匿名用户',
          date: r.created_at ? r.created_at.split('T')[0] : ''
        }
      })
      this.setData({
        companion: companion,
        reviews: reviews
      })
    } catch (err) {
      wx.showToast({ title: '加载失败', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  onBook() {
    wx.navigateTo({
      url: '/pages/patient/create-order/index?companion_id=' + this.companionId
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
  },

  onPreviewCertification() {
    const { companion } = this.data
    if (companion && companion.certificationImageUrl) {
      wx.previewImage({
        urls: [companion.certificationImageUrl],
        current: companion.certificationImageUrl
      })
    }
  }
})
