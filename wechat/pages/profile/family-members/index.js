// [F-05] Family members management page (我的家人)
const {
  listFamilyMembers,
  createFamilyMember,
  updateFamilyMember,
  deleteFamilyMember,
} = require('../../../services/familyMember')
const { RELATION_OPTIONS, relationLabel, relationLabelI18n, relationOptionsI18n } = require('../../../utils/familyRelation')
const i18n = require('../../../utils/i18n')
const i18nBehavior = require('../../../behaviors/i18n')

function genderOptionsI18n() {
  return [
    { value: 'unknown', label: i18n.t('familyMembers.genderUnknown') },
    { value: 'male', label: i18n.t('familyMembers.genderMale') },
    { value: 'female', label: i18n.t('familyMembers.genderFemale') }
  ]
}
const GENDER_OPTIONS = genderOptionsI18n()

Page({
  behaviors: [i18nBehavior],
  data: {
    i18nScopes: ['common', 'familyMembers', 'relation'],
    members: [],
    loading: true,
    showForm: false,
    editingId: null,
    form: {
      name: '',
      relation: 'other',
      phone: '',
      gender: 'unknown',
      age: '',
      medical_notes: '',
    },
    relationOptions: RELATION_OPTIONS,
    relationLabels: relationOptionsI18n().map(function (o) { return o.label }),
    relationIndex: RELATION_OPTIONS.length - 1, // default → other
    genderOptions: GENDER_OPTIONS,
    genderLabels: GENDER_OPTIONS.map(function (o) { return o.label }),
    genderIndex: 0,
  },

  onLoad() {
    this.loadMembers()
  },

  onShow() {
    if (!this.data.loading) this.loadMembers()
  },

  async loadMembers() {
    this.setData({ loading: true })
    try {
      const res = await listFamilyMembers()
      const items = (res && res.items) || []
      const enriched = items.map(function (m) {
        return Object.assign({}, m, {
          relation_label: relationLabelI18n(m.relation),
          ageText: (m.age != null) ? i18n.t('familyMembers.ageUnit', { age: m.age }) : ''
        })
      })
      this.setData({ members: enriched })
    } catch (e) {
      wx.showToast({ title: i18n.t('familyMembers.loadFailed'), icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  onAddTap() {
    this.setData({
      showForm: true,
      editingId: null,
      form: {
        name: '',
        relation: 'other',
        phone: '',
        gender: 'unknown',
        age: '',
        medical_notes: '',
      },
      relationIndex: RELATION_OPTIONS.length - 1,
      genderIndex: 0,
    })
  },

  onEditTap(e) {
    const id = e.currentTarget.dataset.id
    const m = this.data.members.find(function (x) { return x.id === id })
    if (!m) return
    const relIdx = Math.max(0, RELATION_OPTIONS.findIndex(function (o) { return o.value === m.relation }))
    const genIdx = Math.max(0, GENDER_OPTIONS.findIndex(function (o) { return o.value === (m.gender || 'unknown') }))
    this.setData({
      showForm: true,
      editingId: id,
      form: {
        name: m.name || '',
        relation: m.relation || 'other',
        phone: m.phone || '',
        gender: m.gender || 'unknown',
        age: m.age == null ? '' : String(m.age),
        medical_notes: m.medical_notes || '',
      },
      relationIndex: relIdx,
      genderIndex: genIdx,
    })
  },

  onCancelForm() {
    this.setData({ showForm: false, editingId: null })
  },

  onNameInput(e) { this.setData({ 'form.name': e.detail.value }) },
  onPhoneInput(e) { this.setData({ 'form.phone': e.detail.value }) },
  onAgeInput(e) { this.setData({ 'form.age': e.detail.value }) },
  onNotesInput(e) { this.setData({ 'form.medical_notes': e.detail.value }) },

  onRelationChange(e) {
    const idx = Number(e.detail.value)
    this.setData({
      relationIndex: idx,
      'form.relation': RELATION_OPTIONS[idx].value,
    })
  },

  onGenderChange(e) {
    const idx = Number(e.detail.value)
    this.setData({
      genderIndex: idx,
      'form.gender': GENDER_OPTIONS[idx].value,
    })
  },

  _validate() {
    const f = this.data.form
    if (!f.name || !f.name.trim()) return i18n.t('familyMembers.fillName')
    if (f.name.trim().length > 50) return i18n.t('familyMembers.nameTooLong')
    if (f.phone && !/^1[3-9]\d{9}$/.test(f.phone)) return i18n.t('familyMembers.invalidPhone')
    if (f.age !== '' && f.age !== null) {
      const n = Number(f.age)
      if (!Number.isInteger(n) || n < 0 || n > 130) return i18n.t('familyMembers.invalidAge')
    }
    return null
  },

  async onSubmit() {
    const err = this._validate()
    if (err) {
      wx.showToast({ title: err, icon: 'none' })
      return
    }
    const f = this.data.form
    const payload = {
      name: f.name.trim(),
      relation: f.relation || 'other',
      gender: f.gender || 'unknown',
    }
    if (f.phone) payload.phone = f.phone.trim()
    if (f.age !== '' && f.age !== null) payload.age = Number(f.age)
    if (f.medical_notes) payload.medical_notes = f.medical_notes.trim()

    try {
      if (this.data.editingId) {
        await updateFamilyMember(this.data.editingId, payload)
        wx.showToast({ title: i18n.t('familyMembers.updated'), icon: 'success' })
      } else {
        await createFamilyMember(payload)
        wx.showToast({ title: i18n.t('familyMembers.added'), icon: 'success' })
      }
      this.setData({ showForm: false, editingId: null })
      await this.loadMembers()
    } catch (e) {
      let msg = i18n.t('familyMembers.saveFailed')
      if (e && e.data && e.data.detail) {
        const d = e.data.detail
        msg = (d && d.message) || (typeof d === 'string' ? d : msg)
      }
      wx.showToast({ title: msg, icon: 'none' })
    }
  },

  async onDeleteTap(e) {
    const id = e.currentTarget.dataset.id
    const res = await wx.showModal({
      title: i18n.t('familyMembers.deleteTitle'),
      content: i18n.t('familyMembers.deleteConfirm'),
      confirmText: i18n.t('familyMembers.delete'),
      confirmColor: '#e53935',
    })
    if (!res.confirm) return
    try {
      await deleteFamilyMember(id)
      wx.showToast({ title: i18n.t('familyMembers.deleted'), icon: 'success' })
      await this.loadMembers()
    } catch (err) {
      wx.showToast({ title: i18n.t('familyMembers.deleteFailed'), icon: 'none' })
    }
  },
})
