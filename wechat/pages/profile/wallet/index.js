var store = require('../../../store/index')
var walletService = require('../../../services/wallet')

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
    this.loadWallet()
  },

  onShow() {
    this.loadWallet()
  },

  async loadWallet() {
    try {
      var summary = await walletService.getWalletSummary()
      var txRes = await walletService.getTransactions()
      var items = (txRes && txRes.items) || []
      var role = this.data.role

      this.setData({
        balance: (summary.balance || 0).toFixed(2),
        totalIncome: (summary.total_income || 0).toFixed(2),
        withdrawn: (summary.withdrawn || 0).toFixed(2),
        records: items.map(function (t) {
          var isRefund = t.payment_type === 'refund'
          return {
            id: t.id,
            title: isRefund ? '订单退款' : (role === 'companion' ? '服务收入' : '订单支付'),
            time: t.created_at ? t.created_at.split('T')[0] : '',
            amount: t.amount ? t.amount.toFixed(2) : '0.00',
            type: isRefund ? 'income' : (role === 'companion' ? 'income' : 'expense')
          }
        })
      })
    } catch (e) {
      console.error('加载钱包失败', e)
    }
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
