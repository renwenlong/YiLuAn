const { getPatientProfile, updatePatientProfile } = require('../../../services/user')
const { updateCompanionProfile } = require('../../../services/companion')
const store = require('../../../store/index')

Page({
  data: {
    role: '',
    emergency_contact: '',
    emergency_phone: '',
    medical_notes: '',
    bio: '',
    service_area: '',
    loading: false,
    saving: false
  },

  onLoad() {
    const state = store.getState()
    var role = (state && state.user && state.user.role) || 'patient'
    this.setData({ role: role })
    this.loadProfile()
  },

  loadProfile() {
    var role = this.data.role
    this.setData({ loading: true })

    if (role === 'patient') {
      getPatientProfile()
        .then((data) => {
          this.setData({
            emergency_contact: data.emergency_contact || '',
            emergency_phone: data.emergency_phone || '',
            medical_notes: data.medical_notes || '',
            loading: false
          })
        })
        .catch(() => {
          this.setData({ loading: false })
        })
    } else if (role === 'companion') {
      var state = store.getState()
      var user = (state && state.user) || {}
      this.setData({
        bio: user.bio || '',
        service_area: user.service_area || '',
        loading: false
      })
    } else {
      this.setData({ loading: false })
    }
  },

  onInputChange(e) {
    var field = e.currentTarget.dataset.field
    var obj = {}
    obj[field] = e.detail.value
    this.setData(obj)
  },

  onSave() {
    var role = this.data.role
    this.setData({ saving: true })

    if (role === 'patient') {
      var patientData = {
        emergency_contact: this.data.emergency_contact,
        emergency_phone: this.data.emergency_phone,
        medical_notes: this.data.medical_notes
      }
      updatePatientProfile(patientData)
        .then(() => {
          this.setData({ saving: false })
          wx.showToast({ title: '保存成功', icon: 'success' })
          setTimeout(function() {
            wx.navigateBack()
          }, 1500)
        })
        .catch(() => {
          this.setData({ saving: false })
          wx.showToast({ title: '保存失败', icon: 'none' })
        })
    } else if (role === 'companion') {
      var companionData = {
        bio: this.data.bio,
        service_area: this.data.service_area
      }
      updateCompanionProfile(companionData)
        .then((data) => {
          this.setData({ saving: false })
          var state = store.getState()
          var user = Object.assign({}, state.user, data)
          store.setState({ user: user })
          wx.showToast({ title: '保存成功', icon: 'success' })
          setTimeout(function() {
            wx.navigateBack()
          }, 1500)
        })
        .catch(() => {
          this.setData({ saving: false })
          wx.showToast({ title: '保存失败', icon: 'none' })
        })
    }
  }
})
