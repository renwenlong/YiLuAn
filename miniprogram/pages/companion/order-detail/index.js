const { getOrderDetail, orderAction } = require('../../../services/order')
const store = require('../../../store/index')
const { ORDER_STATUS } = require('../../../utils/constants')
const { formatPrice, formatDate } = require('../../../utils/format')

Page({
  data: {
    order: null,
    loading: true,
    statusList: ORDER_STATUS
  },

  onLoad(options) {
    this.orderId = options.id
    this.loadOrder()
  },

  onShow() {
    if (this.orderId && !this.data.loading) {
      this.loadOrder()
    }
  },

  async loadOrder() {
    this.setData({ loading: true })
    try {
      const order = await getOrderDetail(this.orderId)
      this.setData({
        order: {
          ...order,
          formattedDate: formatDate(order.date),
          formattedPrice: order.price ? formatPrice(order.price) : ''
        }
      })
    } catch (err) {
      wx.showToast({ title: '加载失败', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  async onAccept() {
    const res = await wx.showModal({
      title: '确认接单',
      content: '确定要接受该订单吗？',
      confirmText: '确认',
      confirmColor: '#4CAF50'
    })
    if (!res.confirm) return

    this.setData({ loading: true })
    try {
      await orderAction(this.orderId, 'accept')
      wx.showToast({ title: '接单成功', icon: 'success' })
      this.loadOrder()
    } catch (err) {
      wx.showToast({ title: '操作失败', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  async onStart() {
    const res = await wx.showModal({
      title: '开始服务',
      content: '确认开始为患者提供陪诊服务？',
      confirmText: '确认',
      confirmColor: '#4CAF50'
    })
    if (!res.confirm) return

    this.setData({ loading: true })
    try {
      await orderAction(this.orderId, 'start')
      wx.showToast({ title: '服务已开始', icon: 'success' })
      this.loadOrder()
    } catch (err) {
      wx.showToast({ title: '操作失败', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  async onComplete() {
    const res = await wx.showModal({
      title: '完成服务',
      content: '确认已完成本次陪诊服务？',
      confirmText: '确认完成',
      confirmColor: '#4CAF50'
    })
    if (!res.confirm) return

    this.setData({ loading: true })
    try {
      await orderAction(this.orderId, 'complete')
      wx.showToast({ title: '服务已完成', icon: 'success' })
      this.loadOrder()
    } catch (err) {
      wx.showToast({ title: '操作失败', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  onChat() {
    wx.navigateTo({
      url: `/pages/chat/room/index?id=${this.orderId}`
    })
  },

  onCallPatient() {
    const { order } = this.data
    if (order && order.patient && order.patient.phone) {
      wx.makePhoneCall({ phoneNumber: order.patient.phone })
    }
  }
})
