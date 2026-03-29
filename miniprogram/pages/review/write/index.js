const { submitReview } = require('../../services/review')
const store = require('../../store/index')

Page({
  data: {
    orderId: '',
    rating: 5,
    content: '',
    loading: false
  },

  onLoad(options) {
    this.setData({ orderId: options.id })
  },

  onRatingChange(e) {
    this.setData({ rating: e.detail.value })
  },

  onInput(e) {
    this.setData({ content: e.detail.value })
  },

  async onSubmit() {
    const { orderId, rating, content } = this.data

    if (!content.trim()) {
      wx.showToast({ title: '请输入评价内容', icon: 'none' })
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
        rating,
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
