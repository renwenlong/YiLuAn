var createOrder = require('../../../services/order').createOrder
var getCompanionDetail = require('../../../services/companion').getCompanionDetail
var getCompanions = require('../../../services/companion').getCompanions
var listFamilyMembers = require('../../../services/familyMember').listFamilyMembers
var relationLabel = require('../../../utils/familyRelation').relationLabel
var SERVICE_TYPES = require('../../../utils/constants').SERVICE_TYPES
var listPublicServicePackages = require('../../../services/servicePackages').listPublicServicePackages
var formatCurrency = require('../../../utils/formatCurrency').formatCurrency
var orderSummary = require('../../../utils/orderSummary')
var stepper = require('../../../utils/stepperState')
var fontScale = require('../../../utils/fontScale')
var store = require('../../../store/index')
var logger = require('../../../utils/logger')
var analytics = require('../../../utils/analytics')
const router = require('../../../utils/router')
const i18n = require('../../../utils/i18n')
const i18nBehavior = require('../../../behaviors/i18n')

Page({
  behaviors: [i18nBehavior],
  data: {
    i18nScopes: ['common', 'createOrder', 'serviceType', 'toast', 'dialog'],
    serviceType: '',
    serviceTypeName: '',
    servicePrice: 0,
    servicePriceText: '¥0.00',
    hospitalId: '',
    hospitalName: '',
    companionId: '',
    companion: null,
    companionCompletedText: '',
    date: '',
    time: '',
    notes: '',
    loading: false,
    showCompanionPicker: false,
    companionList: [],
    loadingCompanions: false,
    // [F-05] family member picker (代他人下单)
    familyMembers: [],            // {id, name, relation, relation_label}
    familyMemberOptions: [i18n.t('createOrder.self')], // display labels for <picker>
    familyMemberIndex: 0,         // 0 = 本人
    familyMemberId: '',
    // [S2-INT-004 prelude] U-1 折叠分步状态机
    currentStep: 1,
    maxReachedStep: 1,
    stepStates: ['active', 'collapsed', 'collapsed', 'collapsed'],
    stepTitles: stepper.STEP_TITLES,
    // 服务类型列表（S2-REQ-003-P5b：onLoad 拉 /public/service-packages、降级 fallback）
    serviceTypes: [
      { code: 'full_accompany', name: i18n.t('serviceType.full_accompany'), price: 299 },
      { code: 'half_accompany', name: i18n.t('serviceType.half_accompany'), price: 199 },
      { code: 'errand', name: i18n.t('serviceType.errand'), price: 149 }
    ],
    // 服务档位是否使用了降级兼底（API 不可达，显示提示）
    servicePackagesFallback: false,
    // 各步骤摘要（接 orderSummary 真源）
    summaryService: '',
    summaryHospital: '',
    summaryDate: '',
    summaryPatient: '',
    // 科室（可选）
    department: '',
    departmentList: [],
    departmentIndex: 0,
    // 时段：上午|下午
    period: '上午',
    // 巨字号
    hugeFont: false,
    fontTokens: fontScale.tokens(false),
    canSubmit: false
  },

  onLoad(options) {
    // [funnel-3] 发起下单 — 进入下单页
    try { analytics.trackFunnel(analytics.FUNNEL_STEPS.ORDER_CREATE_START, { service_type: options && options.type ? String(options.type) : undefined, source: 'create_order_onLoad' }) } catch (_) {}
    var today = new Date()
    var year = today.getFullYear()
    var month = String(today.getMonth() + 1).padStart(2, '0')
    var day = String(today.getDate()).padStart(2, '0')
    var data = { date: year + '-' + month + '-' + day, time: '09:00' }

    if (options.type && SERVICE_TYPES[options.type]) {
      var info = SERVICE_TYPES[options.type]
      data.serviceType = options.type
      data.serviceTypeName = info.label
      data.servicePrice = info.price
      data.servicePriceText = formatCurrency(info.price)
    }

    if (options.hospital_id) {
      data.hospitalId = options.hospital_id
    }
    if (options.hospital_name) {
      data.hospitalName = decodeURIComponent(options.hospital_name)
    }

    this.setData(data)

    // S2-REQ-003-P5b: 拉 /public/service-packages 接口 覆盖默认 3 档
    // (不 出发 出售), 降级 fallback (FALLBACK_PACKAGES 与默认 3 档一致)
    var self = this
    listPublicServicePackages().then(function (pkgs) {
      var isFallback = pkgs.length > 0 && pkgs[0]._fallback === true
      self.setData({
        serviceTypes: pkgs.map(function (p) {
          return { code: p.code, name: p.name, price: p.price }
        }),
        servicePackagesFallback: isFallback
      })
      // 如果 URL 带 type 可在动态档位中重启以 sync名称+价格
      if (self.data.serviceType) {
        var match = pkgs.filter(function (p) { return p.code === self.data.serviceType })[0]
        if (match) {
          self.setData({
            serviceTypeName: match.name,
            servicePrice: match.price,
            servicePriceText: formatCurrency(match.price)
          }, function () { self.recomputeSteps && self.recomputeSteps() })
        }
      }
    })

    if (options.companion_id) {
      this.loadCompanion(options.companion_id)
    }

    this.loadFamilyMembers()

    // [S2-INT-004 prelude] 巨字号偏好 + 首次状态/摘要重算
    try {
      var huge = !!(wx.getStorageSync && wx.getStorageSync('huge_font'))
      this.setData({ hugeFont: huge, fontTokens: fontScale.tokens(huge) })
    } catch (_) {}
    var firstIncomplete = stepper.firstIncompleteStep(this.data)
    var startStep = firstIncomplete === 0 ? 4 : firstIncomplete
    this.setData({ currentStep: startStep, maxReachedStep: Math.max(startStep, this.data.maxReachedStep) })
    this.recomputeSteps()
  },

  // [S2-INT-004 prelude] 重算步骤三态 + 各步摘要 + canSubmit
  recomputeSteps: function () {
    var d = this.data
    var states = stepper.computeStepStates(d.currentStep, d, d.maxReachedStep)
    var summaryService = d.serviceType ? orderSummary.summaryService(d.serviceTypeName, d.servicePrice) : ''
    var summaryHospital = d.hospitalId ? orderSummary.summaryHospital(d.hospitalName, d.department) : ''
    var summaryDate = (d.date && d.period) ? orderSummary.summaryDate(d.date, d.period) : ''
    var patient = this.resolvePatient()
    var summaryPatient = patient ? orderSummary.summaryPatient(patient.name, patient.relation, patient.age) : ''
    this.setData({
      stepStates: states,
      summaryService: summaryService,
      summaryHospital: summaryHospital,
      summaryDate: summaryDate,
      summaryPatient: summaryPatient,
      canSubmit: stepper.canSubmit(d)
    })
  },

  resolvePatient: function () {
    var d = this.data
    if (d.familyMemberId) {
      for (var i = 0; i < d.familyMembers.length; i++) {
        var m = d.familyMembers[i]
        if (m.id === d.familyMemberId) {
          return { name: m.name, relation: relationLabel(m.relation), age: m.age }
        }
      }
    }
    var state = store.getState ? store.getState() : null
    var user = (state && state.user) || {}
    if (user.name) return { name: user.name, relation: i18n.t('createOrder.self'), age: user.age }
    return null
  },

  onSelectServiceType: function (e) {
    var d = e.currentTarget.dataset
    this.setData({
      serviceType: d.code,
      serviceTypeName: d.name,
      servicePrice: Number(d.price),
      servicePriceText: formatCurrency(Number(d.price))
    }, this.recomputeSteps.bind(this))
  },

  onSelectPeriod: function (e) {
    this.setData({ period: e.currentTarget.dataset.period }, this.recomputeSteps.bind(this))
  },

  onChangeHospital: function () {
    router.navigate({ url: '/pages/patient/search-hospital/index?return_to=create-order' })
  },

  onDepartmentChange: function (e) {
    var idx = Number(e.detail.value)
    var dept = this.data.departmentList[idx] || ''
    this.setData({ departmentIndex: idx, department: dept }, this.recomputeSteps.bind(this))
  },

  onNextStep: function () {
    var d = this.data
    if (!stepper.isStepFilled(d.currentStep, d)) {
      wx.showToast({ title: i18n.t('createOrder.finishStepFirst'), icon: 'none' })
      return
    }
    var next = Math.min(d.currentStep + 1, stepper.TOTAL_STEPS)
    this.setData({
      currentStep: next,
      maxReachedStep: Math.max(next, d.maxReachedStep)
    }, this.recomputeSteps.bind(this))
  },

  onStepTap: function (e) {
    var step = Number(e.currentTarget.dataset.step)
    if (step === this.data.currentStep) return
    // 只有 done 步可点回改
    if (!stepper.canNavigateTo(step, this.data)) return
    var self = this
    wx.showModal({
      title: i18n.t('createOrder.confirmBack'),
      content: i18n.t('createOrder.confirmBackContent'),
      success: function (res) {
        if (res.confirm) {
          self.setData({ currentStep: step }, self.recomputeSteps.bind(self))
        }
      }
    })
  },

  onToggleHugeFont: function (e) {
    var huge = !!e.detail.value
    this.setData({ hugeFont: huge, fontTokens: fontScale.tokens(huge) })
    try { wx.setStorageSync && wx.setStorageSync('huge_font', huge) } catch (_) {}
  },

  // [F-05] 拉取当前用户的家人列表，填充 picker
  loadFamilyMembers: function () {
    var self = this
    listFamilyMembers()
      .then(function (res) {
        var items = (res && res.items) || []
        var options = [i18n.t('createOrder.self')].concat(items.map(function (m) {
          return m.name + '（' + relationLabel(m.relation) + '）'
        }))
        self.setData({
          familyMembers: items,
          familyMemberOptions: options,
          familyMemberIndex: 0,
          familyMemberId: ''
        })
      })
      .catch(function () {
        // 静默失败：家人列表只是增强项，不需要阻断下单
      })
  },

  onFamilyMemberChange: function (e) {
    var idx = Number(e.detail.value)
    var id = idx === 0 ? '' : (this.data.familyMembers[idx - 1] && this.data.familyMembers[idx - 1].id) || ''
    this.setData({ familyMemberIndex: idx, familyMemberId: id }, this.recomputeSteps.bind(this))
  },

  onManageFamilyMembers: function () {
    router.navigate({ url: '/pages/profile/family-members/index' })
  },

  loadCompanion(companionId) {
    var self = this
    getCompanionDetail(companionId)
      .then(function (res) {
        self.setData({
          companionId: res.id,
          companion: {
            id: res.id,
            name: res.real_name || res.name || res.user_name || '',
            rating: res.avg_rating || res.rating || 0,
            completed_orders: res.total_orders || 0,
            service_areas: res.service_area ? res.service_area.split('\u3001') : []
          },
          companionCompletedText: i18n.t('createOrder.completedOrders', { count: res.total_orders || 0 })
        })
      })
      .catch(function (err) {
        logger.error('加载陪诊师信息失败', { err: err && (err.message || String(err)) })
      })
  },

  onDateChange(e) {
    this.setData({ date: e.detail.value }, this.recomputeSteps.bind(this))
  },

  onTimeChange(e) {
    this.setData({ time: e.detail.value })
  },

  onNotesInput(e) {
    this.setData({ notes: e.detail.value })
  },

  onChangeCompanion() {
    var self = this
    self.setData({ showCompanionPicker: true, loadingCompanions: true })
    var params = { page_size: 20 }
    if (self.data.hospitalId) {
      params.hospital_id = self.data.hospitalId
    }
    if (self.data.serviceType) {
      params.service_type = self.data.serviceType
    }
    getCompanions(params)
      .then(function (res) {
        var raw = Array.isArray(res) ? res : (res.items || res.data || [])
        var list = raw.map(function (item) {
          return {
            id: item.id,
            name: item.real_name || item.display_name || '',
            rating: item.avg_rating || 0,
            completed_orders: item.total_orders || 0,
            completedText: i18n.t('createOrder.completedOrders', { count: item.total_orders || 0 }),
            service_areas: item.service_area ? item.service_area.split('\u3001') : [],
            bio: item.bio || '',
            verified: item.verification_status === 'approved'
          }
        })
        self.setData({ companionList: list, loadingCompanions: false })
      })
      .catch(function (err) {
        logger.error('加载陪诊师列表失败', { err: err && (err.message || String(err)) })
        self.setData({ loadingCompanions: false })
      })
  },

  onSelectCompanion(e) {
    var id = e.currentTarget.dataset.id
    var list = this.data.companionList
    var selected = null
    for (var i = 0; i < list.length; i++) {
      if (list[i].id === id) {
        selected = list[i]
        break
      }
    }
    if (selected) {
      this.setData({
        companionId: selected.id,
        companion: selected,
        companionCompletedText: selected.completedText || i18n.t('createOrder.completedOrders', { count: selected.completed_orders || 0 }),
        showCompanionPicker: false
      })
    }
  },

  onCloseCompanionPicker() {
    this.setData({ showCompanionPicker: false })
  },

  onSubmit() {
    var d = this.data
    if (d.loading) return
    if (!d.serviceType) {
      wx.showToast({ title: i18n.t('createOrder.missingService'), icon: 'none' })
      return
    }
    if (!d.hospitalId) {
      wx.showToast({ title: i18n.t('createOrder.missingHospital'), icon: 'none' })
      return
    }
    if (!d.date || !d.time) {
      wx.showToast({ title: i18n.t('createOrder.selectDateTime'), icon: 'none' })
      return
    }

    // Check phone binding
    var state = store.getState()
    var user = (state && state.user) || {}
    if (!user.phone) {
      wx.showModal({
        title: i18n.t('createOrder.bindPhoneTitle'),
        content: i18n.t('createOrder.bindPhoneContent'),
        confirmText: i18n.t('createOrder.goBind'),
        success: function (res) {
          if (res.confirm) {
            var currentUrl = '/pages/patient/create-order/index'
              + '?type=' + d.serviceType
              + '&hospital_id=' + d.hospitalId
              + '&hospital_name=' + encodeURIComponent(d.hospitalName)
            if (d.companionId) currentUrl += '&companion_id=' + d.companionId
            router.navigate({
              url: '/pages/profile/bind-phone/index?redirect=' + encodeURIComponent(currentUrl)
            })
          }
        }
      })
      return
    }
    this.setData({ loading: true })
    var orderData = {
      service_type: d.serviceType,
      hospital_id: d.hospitalId,
      appointment_date: d.date,
      appointment_time: d.time
    }
    if (d.notes) orderData.description = d.notes
    if (d.companionId) orderData.companion_id = d.companionId
    // [F-05] 代他人下单：仅在选中具体家人时传
    if (d.familyMemberId) orderData.family_member_id = d.familyMemberId

    var self = this
    createOrder(orderData)
      .then(function (order) {
        self.setData({ loading: false })
        // [funnel-4] 提交订单成功
        try { analytics.trackFunnel(analytics.FUNNEL_STEPS.ORDER_SUBMIT, { order_id: order && order.id ? String(order.id) : undefined, service_type: orderData.service_type, amount_cents: typeof d.servicePrice === 'number' ? Math.round(d.servicePrice * 100) : undefined }) } catch (_) {}
        wx.showToast({ title: i18n.t('createOrder.orderSuccess'), icon: 'success' })
        setTimeout(function () {
          router.redirect({
            url: '/pages/patient/order-detail/index?id=' + order.id + '&need_pay=1'
          })
        }, 1500)
      })
      .catch(function (err) {
        self.setData({ loading: false })
        var msg = i18n.t('createOrder.createFailed')
        if (err && err.data && err.data.detail) msg = err.data.detail
        else if (err && err.message) msg = err.message
        wx.showToast({ title: msg, icon: 'none' })
      })
  }
})
