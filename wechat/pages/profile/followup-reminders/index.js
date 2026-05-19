// [F-07] 我的复诊提醒列表（按 remind_at 升序）
const {
  listMyFollowupReminders,
  cancelFollowupReminder,
} = require('../../../services/followupReminder')

const STATUS_LABEL = {
  pending: '待提醒',
  sent: '已发送',
  cancelled: '已取消',
  failed: '发送失败',
}

function fmt(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  if (isNaN(d.getTime())) return ts
  const pad = (n) => (n < 10 ? '0' + n : '' + n)
  return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate())
    + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes())
}

Page({
  data: {
    items: [],
    loading: true,
  },

  onShow() {
    this.load()
  },

  async load() {
    this.setData({ loading: true })
    try {
      const res = await listMyFollowupReminders()
      const items = ((res && res.items) || []).map(function (r) {
        return Object.assign({}, r, {
          remind_at_display: fmt(r.remind_at),
          status_label: STATUS_LABEL[r.status] || r.status,
          can_cancel: r.status === 'pending',
          order_short: r.order_id ? r.order_id.slice(0, 8) : '',
        })
      })
      this.setData({ items })
    } catch (e) {
      wx.showToast({ title: '加载失败', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  async onCancelTap(ev) {
    const id = ev.currentTarget.dataset.id
    if (!id) return
    const res = await new Promise((resolve) => {
      wx.showModal({
        title: '取消提醒',
        content: '确定要取消该提醒吗？',
        success: (r) => resolve(r),
        fail: () => resolve({ confirm: false }),
      })
    })
    if (!res.confirm) return
    try {
      await cancelFollowupReminder(id)
      wx.showToast({ title: '已取消', icon: 'success' })
      this.load()
    } catch (e) {
      wx.showToast({ title: '取消失败', icon: 'none' })
    }
  },
})
