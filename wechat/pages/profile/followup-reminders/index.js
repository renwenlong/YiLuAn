// [F-07] 我的复诊提醒列表（按 remind_at 升序）
const {
  listMyFollowupReminders,
  cancelFollowupReminder,
} = require('../../../services/followupReminder')
const i18n = require('../../../utils/i18n')
const i18nBehavior = require('../../../behaviors/i18n')

const STATUS_KEY = {
  pending: 'followupReminders.statusPending',
  sent: 'followupReminders.statusSent',
  cancelled: 'followupReminders.statusCancelled',
  failed: 'followupReminders.statusFailed',
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
  behaviors: [i18nBehavior],
  data: {
    i18nScopes: ['common', 'followupReminders'],
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
        var short = r.order_id ? r.order_id.slice(0, 8) : ''
        return Object.assign({}, r, {
          remind_at_display: fmt(r.remind_at),
          status_label: STATUS_KEY[r.status] ? i18n.t(STATUS_KEY[r.status]) : r.status,
          can_cancel: r.status === 'pending',
          order_short: short,
          order_no_text: i18n.t('followupReminders.orderNo', { no: short }),
        })
      })
      this.setData({ items })
    } catch (e) {
      wx.showToast({ title: i18n.t('followupReminders.loadFailed'), icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  async onCancelTap(ev) {
    const id = ev.currentTarget.dataset.id
    if (!id) return
    const res = await new Promise((resolve) => {
      wx.showModal({
        title: i18n.t('followupReminders.cancelTitle'),
        content: i18n.t('followupReminders.cancelConfirm'),
        success: (r) => resolve(r),
        fail: () => resolve({ confirm: false }),
      })
    })
    if (!res.confirm) return
    try {
      await cancelFollowupReminder(id)
      wx.showToast({ title: i18n.t('followupReminders.cancelled'), icon: 'success' })
      this.load()
    } catch (e) {
      wx.showToast({ title: i18n.t('followupReminders.cancelFailed'), icon: 'none' })
    }
  },
})
