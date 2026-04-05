var store = require('../../../store/index')

Page({
  data: {
    role: 'patient',
    balance: '0.00',
    totalIncome: '0.00',
    withdrawn: '0.00',
    amountOptions: [50, 100, 200, 500, 1000, 2000],
    selectedAmount: 0,
    customAmount: '',
    records: []
  },

  onLoad() {
    var state = store.getState()
    var role = (state && state.user && state.user.role) || 'patient'
    this.setData({ role: role })
  },

  onSelectAmount(e) {
    var amount = e.currentTarget.dataset.amount
    this.setData({
      selectedAmount: amount,
      customAmount: ''
    })
  },

  onCustomInput(e) {
    this.setData({
      customAmount: e.detail.value,
      selectedAmount: 0
    })
  },

  onCustomTap() {
    this.setData({ selectedAmount: 0 })
  },

  onRecharge() {
    var amount = this.data.selectedAmount || Number(this.data.customAmount)
    if (!amount || amount <= 0) {
      wx.showToast({ title: '请选择充值金额', icon: 'none' })
      return
    }
    wx.showToast({ title: '充值功能开发中', icon: 'none' })
  },

  onWithdraw() {
    var balance = parseFloat(this.data.balance)
    if (!balance || balance <= 0) {
      wx.showToast({ title: '暂无可提现余额', icon: 'none' })
      return
    }
    wx.showToast({ title: '提现功能开发中', icon: 'none' })
  }
})
