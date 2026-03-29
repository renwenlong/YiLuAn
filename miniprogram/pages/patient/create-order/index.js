const { createOrder } = require('../../../services/order')
const { searchHospitals } = require('../../../services/hospital')
const store = require('../../../store/index')
const { SERVICE_TYPES } = require('../../../utils/constants')

Page({
  data: {
    step: 1,
    serviceType: '',
    hospital: '',
    hospitalName: '',
    date: '',
    time: '',
    notes: '',
    loading: false,
    hospitals: [],
    searchKeyword: '',
    serviceTypes: SERVICE_TYPES
  },

  onLoad() {
    const today = new Date()
    const year = today.getFullYear()
    const month = String(today.getMonth() + 1).padStart(2, '0')
    const day = String(today.getDate()).padStart(2, '0')
    this.setData({ date: `${year}-${month}-${day}`, time: '09:00' })
  },

  onServiceTypeSelect(e) {
    const { type } = e.currentTarget.dataset
    this.setData({ serviceType: type })
  },

  nextStep() {
    const { step, serviceType, hospital, date, time } = this.data
    if (step === 1 && !serviceType) {
      wx.showToast({ title: '请选择服务类型', icon: 'none' })
      return
    }
    if (step === 2 && !hospital) {
      wx.showToast({ title: '请选择医院', icon: 'none' })
      return
    }
    if (step === 3 && (!date || !time)) {
      wx.showToast({ title: '请选择日期和时间', icon: 'none' })
      return
    }
    if (step < 4) {
      this.setData({ step: step + 1 })
    }
  },

  prevStep() {
    const { step } = this.data
    if (step > 1) {
      this.setData({ step: step - 1 })
    }
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

  onSearchInput(e) {
    this.setData({ searchKeyword: e.detail.value })
  },

  async doSearchHospitals() {
    const { searchKeyword } = this.data
    if (!searchKeyword.trim()) return
    this.setData({ loading: true })
    try {
      const hospitals = await searchHospitals({ keyword: searchKeyword })
      this.setData({ hospitals })
    } catch (err) {
      wx.showToast({ title: '搜索失败', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  onHospitalSelect(e) {
    const { id, name } = e.currentTarget.dataset
    this.setData({ hospital: id, hospitalName: name })
  },

  async onSubmit() {
    const { serviceType, hospital, date, time, notes } = this.data
    this.setData({ loading: true })
    try {
      const order = await createOrder({
        serviceType,
        hospitalId: hospital,
        date,
        time,
        notes
      })
      wx.showToast({ title: '订单创建成功', icon: 'success' })
      setTimeout(() => {
        wx.navigateTo({
          url: `/pages/patient/order-detail/index?id=${order.id}`
        })
      }, 1500)
    } catch (err) {
      wx.showToast({ title: err.message || '创建失败', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  }
})
