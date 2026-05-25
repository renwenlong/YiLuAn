var createOrder = require('../../../services/order').createOrder
var getCompanionDetail = require('../../../services/companion').getCompanionDetail
var getCompanions = require('../../../services/companion').getCompanions
var listFamilyMembers = require('../../../services/familyMember').listFamilyMembers
var relationLabel = require('../../../utils/familyRelation').relationLabel
var SERVICE_TYPES = require('../../../utils/constants').SERVICE_TYPES
var formatCurrency = require('../../../utils/formatCurrency').formatCurrency
var store = require('../../../store/index')
var logger = require('../../../utils/logger')
const router = require('../../../utils/router')

Page({
  data: {
    serviceType: '',
    serviceTypeName: '',
    servicePrice: 0,
    servicePriceText: '¥0.00',
    hospitalId: '',
    hospitalName: '',
    companionId: '',
    companion: null,
    date: '',
    time: '',
    notes: '',
    loading: false,
    showCompanionPicker: false,
    companionList: [],
    loadingCompanions: false,
    // [F-05] family member picker (代他人下单)
    familyMembers: [],            // {id, name, relation, relation_label}
    familyMemberOptions: ['本人'], // display labels for <picker>
    familyMemberIndex: 0,         // 0 = 本人
    familyMemberId: ''
  },

  onLoad(options) {
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

    if (options.companion_id) {
      this.loadCompanion(options.companion_id)
    }

    this.loadFamilyMembers()
  },

  // [F-05] 拉取当前用户的家人列表，填充 picker
  loadFamilyMembers: function () {
    var self = this
    listFamilyMembers()
      .then(function (res) {
        var items = (res && res.items) || []
        var options = ['本人'].concat(items.map(function (m) {
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
    this.setData({ familyMemberIndex: idx, familyMemberId: id })
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
          }
        })
      })
      .catch(function (err) {
        logger.error('加载陪诊师信息失败', { err: err && (err.message || String(err)) })
      })
  },

  onDateChange(e) {
    this.setData({ date: e.detail.value })
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
      wx.showToast({ title: '缺少服务类型', icon: 'none' })
      return
    }
    if (!d.hospitalId) {
      wx.showToast({ title: '缺少医院信息', icon: 'none' })
      return
    }
    if (!d.date || !d.time) {
      wx.showToast({ title: '请选择日期和时间', icon: 'none' })
      return
    }

    // Check phone binding
    var state = store.getState()
    var user = (state && state.user) || {}
    if (!user.phone) {
      wx.showModal({
        title: '请先绑定手机号',
        content: '下单前需要绑定手机号，方便陪诊师联系您',
        confirmText: '去绑定',
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
        wx.showToast({ title: '订单创建成功', icon: 'success' })
        setTimeout(function () {
          router.redirect({
            url: '/pages/patient/order-detail/index?id=' + order.id + '&need_pay=1'
          })
        }, 1500)
      })
      .catch(function (err) {
        self.setData({ loading: false })
        var msg = '创建失败'
        if (err && err.data && err.data.detail) msg = err.data.detail
        else if (err && err.message) msg = err.message
        wx.showToast({ title: msg, icon: 'none' })
      })
  }
})
