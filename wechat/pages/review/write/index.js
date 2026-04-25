const { submitReview } = require('../../services/review')
const store = require('../../store/index')

const DIMENSION_LABELS = {
  punctuality: '守时',
  professionalism: '专业',
  communication: '沟通',
  attitude: '态度'
}

Page({
  data: {
    orderId: '',
    // F-04: 4 dimension star ratings (default 5). Total rating computed
    // server-side; we no longer track a single `rating` slider.
    punctuality_rating: 5,
    professionalism_rating: 5,
    communication_rating: 5,
    attitude_rating: 5,
    dimensionLabels: DIMENSION_LABELS,
    // Average shown to user as "总评分" preview (client-side avg, equal weight).
    overallRating: 5,
    content: '',
    loading: false
  },

  onLoad(options) {
    this.setData({ orderId: options.id })
  },

  _recomputeOverall(patch) {
    const next = Object.assign({}, this.data, patch)
    const sum =
      next.punctuality_rating +
      next.professionalism_rating +
      next.communication_rating +
      next.attitude_rating
    const avg = sum / 4
    return Math.round(avg)
  },

  onPunctualityChange(e) {
    const v = e.detail.value
    const overallRating = this._recomputeOverall({ punctuality_rating: v })
    this.setData({ punctuality_rating: v, overallRating })
  },
  onProfessionalismChange(e) {
    const v = e.detail.value
    const overallRating = this._recomputeOverall({ professionalism_rating: v })
    this.setData({ professionalism_rating: v, overallRating })
  },
  onCommunicationChange(e) {
    const v = e.detail.value
    const overallRating = this._recomputeOverall({ communication_rating: v })
    this.setData({ communication_rating: v, overallRating })
  },
  onAttitudeChange(e) {
    const v = e.detail.value
    const overallRating = this._recomputeOverall({ attitude_rating: v })
    this.setData({ attitude_rating: v, overallRating })
  },

  onInput(e) {
    this.setData({ content: e.detail.value })
  },

  async onSubmit() {
    const {
      orderId,
      punctuality_rating,
      professionalism_rating,
      communication_rating,
      attitude_rating,
      content
    } = this.data

    if (!content.trim()) {
      wx.showToast({ title: '请填写评价内容', icon: 'none' })
      return
    }

    if (content.trim().length < 5) {
      wx.showToast({ title: '评价内容至少5个字', icon: 'none' })
      return
    }

    this.setData({ loading: true })
    try {
      await submitReview({
        orderId,
        punctuality_rating,
        professionalism_rating,
        communication_rating,
        attitude_rating,
        content: content.trim()
      })
      wx.showToast({ title: '评价成功', icon: 'success' })
      setTimeout(() => {
        wx.navigateBack()
      }, 1500)
    } catch (err) {
      wx.showToast({ title: err.message || '提交失败', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  }
})
