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

const PAYMENT_STATUS_MAP = {
  unpaid: '待支付',
  paid: '已支付',
  refunded: '已退款'
}

Page({
  data: {
    order: null,
    loading: true,
    // AI-9: 操作锁，防止状态切换瞬间用户重复点击
    actionLoading: false,
    // S3-DEV-001-CONTRACT-UI: 合同/保障 checkbox 默认 unchecked (ADR-0047 §6.3
    // + PRD-003 §5 AC-3 + PIPL/民法典电子合同合规要求, 不允许 "记住选择")
    contractAccepted: false,
    statusList: ORDER_STATUS,
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
    certStatus: null
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
        self.setData({ countdown: '已超时', countdownUrgent: false })
        self._clearCountdown()
        self.loadOrder()
        return
      }
      var hours = Math.floor(diff / 3600000)
      var minutes = Math.floor((diff % 3600000) / 60000)
      self.setData({
        countdown: hours + '小时' + minutes + '分钟',
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
      const serviceLabel = order.service_name_snapshot || svc.label || order.service_type

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
        paymentStatusLabel: PAYMENT_STATUS_MAP[paymentStatus] || paymentStatus,
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
      wx.showToast({ title: '加载失败', icon: 'none' })
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
        title: '合同确认网络异常,请检查后重试',
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
              wx.showToast({ title: '合同加载失败', icon: 'none' })
            }
          },
          fail: function () {
            wx.showToast({ title: '合同加载失败', icon: 'none' })
          }
        })
      } else {
        // status != 'active' — 按 status 显示对应文案
        var msg = '合同尚未生成,请稍后再查看'
        if (detail.status === 'generation_failed' || detail.status === 'generation_permanently_failed') {
          msg = '合同生成失败,客服已介入处理'
        } else if (detail.status === 'manually_invalidated') {
          msg = '合同已作废,请联系客服'
        }
        wx.showToast({ title: msg, icon: 'none', duration: 2500 })
      }
    } catch (err) {
      wx.showToast({ title: '合同详情加载失败', icon: 'none' })
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
      title: '陪诊责任险服务条款',
      content: '本服务由医路安平台合作保险公司承保,保障范围包括陪诊期间意外医疗等. S3 灰度阶段保险条款为静态版本,正式版以理赔时实际生效条款为准. 如有问题请联系客服.',
      showCancel: false,
      confirmText: '我已了解'
    })
  },

  async onPay() {
    var order = this.data.order
    var priceText = order.formattedPrice || formatCurrency(order.price)
    const res = await wx.showModal({
      title: '确认支付',
      content: '支付 ' + priceText,
      confirmText: '确认支付',
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
        var msg = '支付失败'
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
      title: '确认开始服务',
      content: '确认后服务正式开始，如需取消将退还50%费用',
      confirmText: '确认开始',
      confirmColor: '#4CAF50'
    })
    if (!res.confirm) return

    if (this.data.actionLoading) return
    this.setData({ actionLoading: true })
    try {
      await orderAction(this.orderId, 'confirm-start')
      wx.showToast({ title: '服务已开始', icon: 'success' })
      this.loadOrder()
    } catch (err) {
      var msg = '操作失败'
      if (err && err.data && err.data.detail) msg = err.data.detail
      wx.showToast({ title: msg, icon: 'none' })
    } finally {
      this.setData({ actionLoading: false })
    }
  },

  async onCancel() {
    var order = this.data.order
    var content = '确定要取消该订单吗？'
    if (order.payment_status === 'paid') {
      content = '取消后将全额退款，确定要取消吗？'
    }
    const res = await wx.showModal({
      title: '确认取消',
      content: content,
      confirmText: '确认取消',
      confirmColor: '#e53935'
    })
    if (!res.confirm) return

    if (this.data.actionLoading) return
    this.setData({ actionLoading: true })
    try {
      await orderAction(this.orderId, 'cancel')
      wx.showToast({ title: '已取消', icon: 'success' })
      this.loadOrder()
    } catch (err) {
      wx.showToast({ title: '操作失败', icon: 'none' })
    } finally {
      this.setData({ actionLoading: false })
    }
  },

  async onCancelInProgress() {
    var order = this.data.order
    var content = '服务已开始，取消将退还50%费用，确定要取消吗？'
    const res = await wx.showModal({
      title: '确认取消',
      content: content,
      confirmText: '确认取消',
      confirmColor: '#e53935'
    })
    if (!res.confirm) return

    if (this.data.actionLoading) return
    this.setData({ actionLoading: true })
    try {
      await orderAction(this.orderId, 'cancel')
      wx.showToast({ title: '已取消', icon: 'success' })
      this.loadOrder()
    } catch (err) {
      wx.showToast({ title: '操作失败', icon: 'none' })
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
        title: '创建复诊提醒',
        content: '默认在 7 天后提醒。点击“确定”即创建。',
        editable: true,
        placeholderText: '备注（可选，如：取报告 / 复查血常规）',
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
      wx.showToast({ title: '已创建', icon: 'success' })
    } catch (e) {
      wx.showToast({ title: '创建失败', icon: 'none' })
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
      var msg = '呼叫失败'
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
      }
    })
  }
})
