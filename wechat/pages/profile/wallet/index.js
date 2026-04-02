Page({
  data: {
    balance: '0.00',
    amountOptions: [50, 100, 200, 500, 1000, 2000],
    selectedAmount: 0,
    customAmount: '',
    records: []
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
  }
})
