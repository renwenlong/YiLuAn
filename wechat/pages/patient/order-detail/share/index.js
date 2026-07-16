// pages/patient/order-share/index.js
// ANDROID-DEV-WX-SHARE-ENTRY — 小程序发起端：患者为订单创建/管理家属分享。
// 对齐 iOS ShareService.createShare/listShares/revokeShare（Owner 路径，本人 access token）。
// 后端约束：同订单 active token 上限 3，第 4 个自动 revoke 最老一枚。

const { createShare, listShares, revokeShare } = require('../../../../services/share')
const i18n = require('../../../../utils/i18n')
const i18nBehavior = require('../../../../behaviors/i18n')
const { formatDate } = require('../../../../utils/format')

Page({
  behaviors: [i18nBehavior],
  i18nScopes: ['common', 'shareEntry', 'shareScope'],

  data: {
    i18nScopes: ['common', 'shareEntry', 'shareScope'],
    loading: true,
    creating: false,
    scope: 'full', // 'full' | 'progress_only'
    scopeOptions: ['full', 'progress_only'],
    scopeIndex: 0,
    scopeDisplay: [], // picker range，随语言刷新
    shares: [], // [{ id, share_token, share_url, share_scope, share_expires_at, expiresText }]
    activeCount: 0,
    revokingId: '',
    activeCountText: '',
  },

  onLoad(options) {
    this.orderId = options.id || options.orderId
    if (!this.orderId) {
      wx.showToast({ icon: 'none', title: i18n.t('shareEntry.errLoadFailed') })
      return
    }
    this._refreshScopeDisplay()
    this._loadShares()
  },

  async _loadShares() {
    this.setData({ loading: true })
    try {
      const resp = await listShares(this.orderId)
      this._applyList(resp)
    } catch (e) {
      wx.showToast({ icon: 'none', title: i18n.t('shareEntry.errLoadFailed') })
    } finally {
      this.setData({ loading: false })
    }
  },

  _applyList(resp) {
    const items = (resp && resp.items) || []
    const shares = items.map(it => ({
      id: it.id,
      share_token: it.share_token,
      share_url: it.share_url,
      share_scope: it.share_scope,
      share_expires_at: it.share_expires_at,
      expiresText: it.share_expires_at ? formatDate(it.share_expires_at) : '',
    }))
    const activeCount =
      resp && typeof resp.share_active_count === 'number'
        ? resp.share_active_count
        : shares.length
    this.setData({
      shares,
      activeCount,
      activeCountText: i18n.t('shareEntry.activeCount', { n: activeCount }),
    })
  },

  // picker range 显示文案随语言刷新（i18nBehavior 切换语言时 t 会更新，
  // 但 scopeDisplay 是 js 层数组，需显式重算）。
  _refreshScopeDisplay() {
    this.setData({
      scopeDisplay: [i18n.t('shareScope.full'), i18n.t('shareScope.progressOnly')],
    })
  },

  onScopeChange(e) {
    const idx = Number(e.detail.value)
    this.setData({ scopeIndex: idx, scope: this.data.scopeOptions[idx] })
  },

  async onCreate() {
    if (this.data.creating) return
    this.setData({ creating: true })
    try {
      const resp = await createShare(this.orderId, this.data.scope)
      // 创建成功后重拉列表，拿到最新 active_count（后端可能自动 revoke 最老）。
      await this._loadShares()
      // 新链接直接复制到剪贴板，降低操作摩擦。
      if (resp && resp.share_url) {
        wx.setClipboardData({
          data: resp.share_url,
          success: () => {
            wx.showToast({ icon: 'success', title: i18n.t('shareEntry.copied') })
          },
        })
      }
    } catch (e) {
      wx.showToast({ icon: 'none', title: i18n.t('shareEntry.errCreateFailed') })
    } finally {
      this.setData({ creating: false })
    }
  },

  onCopy(e) {
    const url = e.currentTarget.dataset.url
    if (!url) return
    wx.setClipboardData({
      data: url,
      success: () => {
        wx.showToast({ icon: 'success', title: i18n.t('shareEntry.copied') })
      },
    })
  },

  onRevoke(e) {
    const tokenId = e.currentTarget.dataset.id
    if (!tokenId) return
    const self = this
    wx.showModal({
      content: i18n.t('shareEntry.revokeConfirm'),
      confirmText: i18n.t('shareEntry.revoke'),
      cancelText: i18n.t('common.cancel'),
      success(res) {
        if (res.confirm) self._doRevoke(tokenId)
      },
    })
  },

  async _doRevoke(tokenId) {
    this.setData({ revokingId: tokenId })
    try {
      await revokeShare(this.orderId, tokenId)
      await this._loadShares()
      wx.showToast({ icon: 'success', title: i18n.t('shareEntry.revoked') })
    } catch (e) {
      wx.showToast({ icon: 'none', title: i18n.t('shareEntry.errRevokeFailed') })
    } finally {
      this.setData({ revokingId: '' })
    }
  },
})
