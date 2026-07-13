const { getOrderDetail, orderAction, payOrder, requestWechatPayment } = require('../../../services/order')
const { acceptContract, getContract } = require('../../../services/contract')
const { getOrderReview } = require('../../../services/review')
const { createFollowupReminder } = require('../../../services/followupReminder')
const {
  listEmergencyContacts,
  getEmergencyHotline,
  triggerEmergencyEvent,
} = require('../../../services/emergency')
// S3-DEV-003-TRUST-UI-WX: 订单付款前 4 信任卡 precheck-status + WS 推送.
// 本 task 范围仅 cert card (4 cert 字段 + 3 状态 + precheck.status.updated event, envelope 含 cert 状态语义).
// 后台奇意 cert/contract/insurance/preparation 4 card 汇总返 — 现阶段仅渲染 cert.
const { getOrderPrecheckStatus } = require('../../../services/precheck')
const precheckWs = require('../../../services/precheckWs')
const store = require('../../../store/index')
const router = require('../../../utils/router')
const { ORDER_STATUS, SERVICE_TYPES } = require('../../../utils/constants')
const { formatPrice, formatDate } = require('../../../utils/format')
const { formatCurrency } = require('../../../utils/formatCurrency')
const { relationLabel } = require('../../../utils/familyRelation')
const { isCountdownUrgent } = require('./utils/countdown')
const i18n = require('../../../utils/i18n')
const i18nBehavior = require('../../../behaviors/i18n')

// 支付状态 → i18n key（渲染时现算）
var PAYMENT_STATUS_KEY = {
  unpaid: 'orderDetail.payUnpaid',
  paid: 'orderDetail.payPaid',
  refunded: 'orderDetail.payRefunded'
}

Page({
  behaviors: [i18nBehavior],
  data: {
    i18nScopes: ['common', 'orderDetail', 'orderStatus', 'serviceType'],
    order: null,
    loading: true,
    // AI-9: 操作锁，防止状态切换瞬间用户重复点击
    actionLoading: false,
    // S3-DEV-001-CONTRACT-UI: 合同/保障 checkbox 默认 unchecked (ADR-0047 §6.3
    // + PRD-003 §5 AC-3 + PIPL/民法典电子合同合规要求, 不允许 "记住选择")
    contractAccepted: false,
    statusList: ORDER_STATUS,
    statusLabelText: '',
    serviceLabel: '',
    paymentStatusLabel: '',
    paymentStatusClass: '',
    countdown: '',
    countdownUrgent: false,
    // [F-05] family_member relation 中文 label（按需填充）
    familyRelationLabel: '',
    // [F-03] Emergency call
    showEmergency: false,
    emergencyContacts: [],
    emergencyHotline: '',
    // S3-DEV-003-TRUST-UI-WX: cert 信任卡 (companion_cert_status sub-object 仅).
    // null = 未拉, 不渲染 <cert-card>; 拉后为 object even when ready=false.
    certStatus: null,
    // S3-DEV-003-TRUST-UI-WX-POLLING-FALLBACK: WS 断时 30s 轮询 fallback 状态
    // (跨端对齐 iOS PrecheckViewModel.isPollingFallback @Published).
    // true → 显示 "轮询中" indicator (类 iOS "轮询中" orange label).
    // 永久失败 (4001/4003/4004/4011) 不进入此态, 由 precheckWs logger.warn.
    isPollingFallback: false
  },

  onLoad(options) {
    this.orderId = options.id
    this.needPay = options.need_pay === '1'
    this.loadOrder()
    // S3-DEV-003-TRUST-UI-WX: 启动 precheck WS 并发拉 cert status.
    this._loadPrecheck()
    this._connectPrecheckWs()
  },

  onShow() {
    if (this.orderId && !this.data.loading) {
      this.loadOrder()
    }
  },

  onHide() {
    this._clearCountdown()
  },

  onUnload() {
    this._clearCountdown()
    // S3-DEV-003-TRUST-UI-WX: 页面退出时 disconnect precheck WS, 避免 socket leak.
    precheckWs.disconnect()
  },

  _clearCountdown() {
    if (this._countdownTimer) {
      clearInterval(this._countdownTimer)
      this._countdownTimer = null
    }
  },

  _startCountdown(expiresAt) {
    this._clearCountdown()
    if (!expiresAt) return

    var self = this
    var expTime = new Date(expiresAt).getTime()

    function update() {
      var now = Date.now()
      var diff = expTime - now
      if (diff <= 0) {
        self.setData({ countdown: i18n.t('orderDetail.timedOut'), countdownUrgent: false })
        self._clearCountdown()
        self.loadOrder()
        return
      }
      var hours = Math.floor(diff / 3600000)
      var minutes = Math.floor((diff % 3600000) / 60000)
      self.setData({
        countdown: i18n.t('orderDetail.countdownHm', { hours: hours, minutes: minutes }),
        countdownUrgent: isCountdownUrgent(diff)
      })
    }

    update()
    this._countdownTimer = setInterval(update, 60000)
    // 测试运行时别让 timer 钉住 node 事件环（jest "open handle" warnings）。
    // 小程序运行时 setInterval 返回整数，不存在 .unref 方法，这个 check 安全。
    if (this._countdownTimer && typeof this._countdownTimer.unref === 'function') {
      this._countdownTimer.unref()
    }
  },

  async loadOrder() {
    this.setData({ loading: true })
    try {
      const order = await getOrderDetail(this.orderId)
      // S2-REQ-003-P5b: 优先使用 order.service_name_snapshot (P3 快照，
      // admin 改名改价后历史订单仍显示下单瞬间的看名称)，
      // 无快照 fallback 到 SERVICE_TYPES dict (兼容历史订单)。
      const svc = SERVICE_TYPES[order.service_type] || {}
      var svcI18n = order.service_type ? i18n.t('serviceType.' + order.service_type) : ''
      if (svcI18n === 'serviceType.' + order.service_type) svcI18n = ''
      const serviceLabel = order.service_name_snapshot || svcI18n || svc.label || order.service_type
      var statusI18n = order.status ? i18n.t('orderStatus.' + order.status) : ''
      if (statusI18n === 'orderStatus.' + order.status) statusI18n = order.status

      var review = null
      if (order.status === 'reviewed' || order.status === 'completed') {
        try {
          review = await getOrderReview(this.orderId)
        } catch (e) {
          // 404 = no review yet
        }
      }

      var paymentStatus = order.payment_status || 'unpaid'
      var famLabel = order.family_member ? relationLabel(order.family_member.relation) : ''
      this.setData({
        order: {
          ...order,
          review: review,
          formattedDate: formatDate(order.appointment_date),
          // S2-REQ-003-P5b fix (魈建议): 显式优先 servicePriceSnapshot, fallback order.price
          // (P3 后 order.price = snapshot 所写入, 两值相同; 显式读 snapshot 文档化意图)
          formattedPrice: order.service_price_snapshot !== undefined && order.service_price_snapshot !== null
            ? formatCurrency(order.service_price_snapshot)
            : (order.price !== undefined && order.price !== null ? formatCurrency(order.price) : ''),
          timelineIndex: order.timeline_index
        },
        serviceLabel: serviceLabel,
        statusLabelText: statusI18n,
        paymentStatusLabel: i18n.t(PAYMENT_STATUS_KEY[paymentStatus] || '') || paymentStatus,
        paymentStatusClass: paymentStatus,
        familyRelationLabel: famLabel
      })

      // Start countdown if order is created and has expires_at
      if (order.status === 'created' && order.expires_at) {
        this._startCountdown(order.expires_at)
      } else {
        this._clearCountdown()
      }

      // Auto-trigger payment prompt after order creation
      if (this.needPay && paymentStatus === 'unpaid') {
        this.needPay = false
        this.onPay()
      }
    } catch (err) {
      wx.showToast({ title: i18n.t('orderDetail.loadFailed'), icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  /**
   * S3-DEV-001-CONTRACT-UI: 用户点 checkbox 切换勾选状态.
   *
   * 勾选时立即调 POST /accept 写 user_audit_logs.contract_acceptance_clicked
   * (ADR-0047 §3.5 PIPL/民法典电子合同取证, 服务端记录 UA + IP + template_version).
   *
   * 失败不阻断 UI 解锁 — toast 提示但 contractAccepted 仍 true, 让用户能继续
   * 支付; 服务端有 cron 兜底重试 audit log 写入. 不要因 audit 网络抖动阻死支付
   * 链路 (PRD-003 §5 业务诉求).
   *
   * 取消勾选 (再点一次) 不调 /accept (因为没 "取消勾选" audit event, 重新勾
   * 则再调一次, 重复 audit 是 ADR-0047 §3.5 取证要求不去重).
   */
  async onToggleContractAccept() {
    var order = this.data.order
    if (!order || !order.contract_id) return
    var newChecked = !this.data.contractAccepted
    this.setData({ contractAccepted: newChecked })
    if (!newChecked) return  // 取消勾选不发 audit
    try {
      await acceptContract(order.contract_id)
    } catch (err) {
      // audit 失败不阻断 UI; 但提示用户网络可能不稳
      wx.showToast({
        title: i18n.t('orderDetail.contractNetErr'),
        icon: 'none',
        duration: 2000
      })
      // 不回滚 contractAccepted — UI 解锁状态保持, 服务端 cron 兜底
    }
  },

  /**
   * S3-DEV-001-CONTRACT-UI: 点 "《医路安陪诊服务合同》" 链接 → 取 signed URL → 系统浏览器打开.
   *
   * 服务端会同时写 user_audit_logs.contract_viewed (PIPL 取证).
   */
  async onViewContract() {
    var order = this.data.order
    if (!order || !order.contract_id) return
    try {
      var detail = await getContract(order.contract_id)
      if (detail.signed_url) {
        // 微信小程序无 iframe; 用 wx.previewImage 不行 (PDF), 用 wx.downloadFile + openDocument 走系统预览
        wx.downloadFile({
          url: detail.signed_url,
          success: function (res) {
            if (res.statusCode === 200) {
              wx.openDocument({
                filePath: res.tempFilePath,
                fileType: 'pdf',
                showMenu: true,
              })
            } else {
              wx.showToast({ title: i18n.t('orderDetail.contractLoadFailed'), icon: 'none' })
            }
          },
          fail: function () {
            wx.showToast({ title: i18n.t('orderDetail.contractLoadFailed'), icon: 'none' })
          }
        })
      } else {
        // status != 'active' — 按 status 显示对应文案
        var msg = i18n.t('orderDetail.contractNotReady')
        if (detail.status === 'generation_failed' || detail.status === 'generation_permanently_failed') {
          msg = i18n.t('orderDetail.contractGenFailed')
        } else if (detail.status === 'manually_invalidated') {
          msg = i18n.t('orderDetail.contractVoided')
        }
        wx.showToast({ title: msg, icon: 'none', duration: 2500 })
      }
    } catch (err) {
      wx.showToast({ title: i18n.t('orderDetail.contractDetailFailed'), icon: 'none' })
    }
  },

  /**
   * S3-DEV-001-CONTRACT-UI: 点 "《陪诊责任险服务条款》" 链接 → 静态条款 modal.
   *
   * 当前 S3 阶段保险走 PLACEHOLDER vendor (ADR-0047 r3), 条款文案静态;
   * 真 vendor 接入后会切到 GET /api/v1/insurance-records/{id}/terms 端点
   * (BACKLOG-INSURANCE-VENDOR-TERMS-ENDPOINT).
   */
  onViewInsuranceTerms() {
    wx.showModal({
      title: i18n.t('orderDetail.insuranceTitle'),
      content: i18n.t('orderDetail.insuranceContent'),
      showCancel: false,
      confirmText: i18n.t('orderDetail.gotIt')
    })
  },

  async onPay() {
    var order = this.data.order
    var priceText = order.formattedPrice || formatCurrency(order.price)
    const res = await wx.showModal({
      title: i18n.t('orderDetail.confirmPay'),
      content: i18n.t('orderDetail.payContent', { price: priceText }),
      confirmText: i18n.t('orderDetail.confirmPay'),
      confirmColor: '#4CAF50'
    })
    if (!res.confirm) return

    if (this.data.actionLoading) return
    this.setData({ actionLoading: true })
    try {
      // Step 1: Create prepay order on backend
      var payResult = await payOrder(this.orderId)

      // Step 2: Call wx.requestPayment (skipped for mock provider)
      await requestWechatPayment(payResult)

      // Step 3: Navigate to pay-result page on success
      router.redirect({
        url: '/pages/patient/pay-result/index?status=success&order_id=' + this.orderId
      })
    } catch (err) {
      if (err && err.cancelled) {
        // User cancelled payment
        router.redirect({
          url: '/pages/patient/pay-result/index?status=cancel&order_id=' + this.orderId
        })
      } else {
        // Payment failed
        var msg = i18n.t('orderDetail.payFailed')
        if (err && err.data && err.data.detail) msg = err.data.detail
        if (err && err.errMsg) msg = err.errMsg
        router.redirect({
          url: '/pages/patient/pay-result/index?status=fail&order_id=' + this.orderId + '&msg=' + encodeURIComponent(msg)
        })
      }
    } finally {
      this.setData({ actionLoading: false })
    }
  },

  async onConfirmStart() {
    const res = await wx.showModal({
      title: i18n.t('orderDetail.confirmStartTitle'),
      content: i18n.t('orderDetail.confirmStartContent'),
      confirmText: i18n.t('orderDetail.confirmStartBtn'),
      confirmColor: '#4CAF50'
    })
    if (!res.confirm) return

    if (this.data.actionLoading) return
    this.setData({ actionLoading: true })
    try {
      await orderAction(this.orderId, 'confirm-start')
      wx.showToast({ title: i18n.t('orderDetail.serviceStarted'), icon: 'success' })
      this.loadOrder()
    } catch (err) {
      var msg = i18n.t('orderDetail.opFailed')
      if (err && err.data && err.data.detail) msg = err.data.detail
      wx.showToast({ title: msg, icon: 'none' })
    } finally {
      this.setData({ actionLoading: false })
    }
  },

  async onCancel() {
    var order = this.data.order
    var content = i18n.t('orderDetail.cancelConfirmDefault')
    if (order.payment_status === 'paid') {
      content = i18n.t('orderDetail.cancelConfirmRefundFull')
    }
    const res = await wx.showModal({
      title: i18n.t('orderDetail.confirmCancelTitle'),
      content: content,
      confirmText: i18n.t('orderDetail.confirmCancelBtn'),
      confirmColor: '#e53935'
    })
    if (!res.confirm) return

    if (this.data.actionLoading) return
    this.setData({ actionLoading: true })
    try {
      await orderAction(this.orderId, 'cancel')
      wx.showToast({ title: i18n.t('orderDetail.cancelled'), icon: 'success' })
      this.loadOrder()
    } catch (err) {
      wx.showToast({ title: i18n.t('orderDetail.opFailed'), icon: 'none' })
    } finally {
      this.setData({ actionLoading: false })
    }
  },

  async onCancelInProgress() {
    var order = this.data.order
    var content = i18n.t('orderDetail.cancelConfirmInProgress')
    const res = await wx.showModal({
      title: i18n.t('orderDetail.confirmCancelTitle'),
      content: content,
      confirmText: i18n.t('orderDetail.confirmCancelBtn'),
      confirmColor: '#e53935'
    })
    if (!res.confirm) return

    if (this.data.actionLoading) return
    this.setData({ actionLoading: true })
    try {
      await orderAction(this.orderId, 'cancel')
      wx.showToast({ title: i18n.t('orderDetail.cancelled'), icon: 'success' })
      this.loadOrder()
    } catch (err) {
      wx.showToast({ title: i18n.t('orderDetail.opFailed'), icon: 'none' })
    } finally {
      this.setData({ actionLoading: false })
    }
  },

  onChat() {
    router.navigate({
      url: `/pages/chat/room/index?id=${this.orderId}`
    })
  },

  onReview() {
    router.navigate({
      url: `/pages/review/write/index?id=${this.orderId}`
    })
  },

  onCallCompanion() {
    const { order } = this.data
    if (order && order.companion && order.companion.phone) {
      wx.makePhoneCall({ phoneNumber: order.companion.phone })
    }
  },

  onReorder() {
    const { order } = this.data
    if (!order) return
    router.navigate({
      url: '/pages/patient/create-order/index?hospital_id=' + order.hospital_id +
        '&service_type=' + order.service_type
    })
  },

  // [F-07] 创建复诊提醒 ------------------------------------------------
  // 简化交互：默认 7 天后同一时间；note 用 prompt 可选填。
  // 后续可接入原生时间选择器（当前 MVP 对齐 iOS）。
  async onCreateFollowup() {
    const { order } = this.data
    if (!order || !order.id) return

    const noteRes = await new Promise((resolve) => {
      wx.showModal({
        title: i18n.t('orderDetail.followupTitle'),
        content: i18n.t('orderDetail.followupContent'),
        editable: true,
        placeholderText: i18n.t('orderDetail.followupPlaceholder'),
        success: (r) => resolve(r),
        fail: () => resolve({ confirm: false }),
      })
    })
    if (!noteRes.confirm) return

    const remindAt = new Date(Date.now() + 7 * 24 * 3600 * 1000).toISOString()
    try {
      await createFollowupReminder(order.id, {
        order_id: order.id,
        remind_at: remindAt,
        note: (noteRes.content || '').slice(0, 140) || null,
      })
      wx.showToast({ title: i18n.t('orderDetail.created'), icon: 'success' })
    } catch (e) {
      wx.showToast({ title: i18n.t('orderDetail.createFailed'), icon: 'none' })
    }
  },

  // [F-03] Emergency call ----------------------------------------------
  async onEmergencyTap() {
    this.setData({ showEmergency: true })
    try {
      const [contacts, hotline] = await Promise.all([
        listEmergencyContacts().catch(() => []),
        getEmergencyHotline().catch(() => ({ hotline: '' })),
      ])
      this.setData({
        emergencyContacts: contacts || [],
        emergencyHotline: (hotline && hotline.hotline) || '',
      })
    } catch (e) {
      // surface but keep panel open with whatever loaded
    }
  },

  onEmergencyClose() {
    this.setData({ showEmergency: false })
  },

  async onCallContact(e) {
    const { id } = e.currentTarget.dataset
    await this._fireEmergency({ contact_id: id })
  },

  async onCallHotline() {
    await this._fireEmergency({ hotline: true })
  },

  onManageContacts() {
    this.setData({ showEmergency: false })
    router.navigate({ url: '/pages/profile/emergency-contacts/index' })
  },

  async _fireEmergency(target) {
    var payload = Object.assign({ order_id: this.orderId }, target)
    try {
      const result = await triggerEmergencyEvent(payload)
      this.setData({ showEmergency: false })
      if (result && result.phone_to_call) {
        wx.makePhoneCall({ phoneNumber: result.phone_to_call })
      }
    } catch (err) {
      var msg = i18n.t('orderDetail.callFailed')
      if (err && err.data && err.data.detail) {
        var d = err.data.detail
        msg = (d && d.message) || (typeof d === 'string' ? d : msg)
      }
      wx.showToast({ title: msg, icon: 'none' })
    }
  },

  // ============================================================
  // S3-DEV-003-TRUST-UI-WX: precheck cert card load + WS hot-refresh
  // ============================================================

  /**
   * 拉 GET /api/v1/users/orders/{order_id}/precheck-status,
   * 取 companion_cert_status sub-object 填进 data.certStatus.
   * 路径压平 — 跳过 cache miss / 404 / 403 仅 logger.warn 不弹反,
   * cert card 用 null 隐藏, 不阻订单详情主流程.
   */
  async _loadPrecheck() {
    if (!this.orderId) return
    try {
      const summary = await getOrderPrecheckStatus(this.orderId)
      // backend OrderPrecheckSummaryView 结构: { companion_cert_status: {...}, ... }
      this.setData({
        certStatus: (summary && summary.companion_cert_status) || null
      })
    } catch (err) {
      // 404 ABAC mask / 403 / network: cert card 隐藏, 不弹反.
      // Do not console.warn here (生产 noise); fall through silently.
    }
  },

  /**
   * 连 precheck WS 推送, 收任何 precheck.* event 后重拉 GET
   * (WS 是触发器, HTTP 是 source of truth — design §3.4).
   *
   * S3-DEV-003-TRUST-UI-WX-POLLING-FALLBACK 增量:
   * - onShouldRefresh: polling tick 触发 _loadPrecheck (HTTP 路径同 WS event)
   * - onConnectionState: precheckWs 上报 isPollingFallback / permanentFailure,
   *   page setData 反映到 UI indicator.
   */
  _connectPrecheckWs() {
    if (!this.orderId) return
    var self = this
    precheckWs.connect({
      orderId: this.orderId,
      onEvent: function (evt) {
        // 3 event 类型: precheck.status.updated / .all_ready / .blocked
        // 任一 event 老老实实 重拉 HTTP, 不拼 payload (避免 front-end
        // 重复后端 ABAC 逻辑).
        if (!evt) return
        var ev = evt.event
        if (ev === 'precheck.status.updated'
            || ev === 'precheck.all_ready'
            || ev === 'precheck.blocked') {
          self._loadPrecheck()
        }
      },
      // Polling tick 触发 HTTP refresh (同 WS event 复用路径).
      onShouldRefresh: function () {
        return self._loadPrecheck()
      },
      // WS 状态变化 → 反映 UI fallback indicator (跨端对齐 iOS isPollingFallback).
      onConnectionState: function (state) {
        if (!state) return
        // 永久失败 (4001/4003/4004/4011) 不显示 "轮询中", precheckWs 已 logger.warn,
        // page 保持 isPollingFallback=false (无 fallback 可言, 报错由 logger 处理).
        if (state.permanentFailure) {
          self.setData({ isPollingFallback: false })
          return
        }
        self.setData({ isPollingFallback: !!state.isPollingFallback })
      }
    })
  }
})
