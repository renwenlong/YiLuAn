// [F-05] Family members management page (我的家人)
const {
  listFamilyMembers,
  createFamilyMember,
  updateFamilyMember,
  deleteFamilyMember,
} = require('../../../services/familyMember')
const { RELATION_OPTIONS, relationLabel } = require('../../../utils/familyRelation')

const GENDER_OPTIONS = [
  { value: 'unknown', label: '未知' },
  { value: 'male', label: '男' },
  { value: 'female', label: '女' },
]

Page({
  data: {
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
    relationLabels: RELATION_OPTIONS.map(function (o) { return o.label }),
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
        return Object.assign({}, m, { relation_label: relationLabel(m.relation) })
      })
      this.setData({ members: enriched })
    } catch (e) {
      wx.showToast({ title: '加载失败', icon: 'none' })
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
    if (!f.name || !f.name.trim()) return '请填写姓名'
    if (f.name.trim().length > 50) return '姓名不超过 50 字'
    if (f.phone && !/^1[3-9]\d{9}$/.test(f.phone)) return '请填写正确手机号'
    if (f.age !== '' && f.age !== null) {
      const n = Number(f.age)
      if (!Number.isInteger(n) || n < 0 || n > 130) return '年龄需为 0-130 的整数'
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
        wx.showToast({ title: '已更新', icon: 'success' })
      } else {
        await createFamilyMember(payload)
        wx.showToast({ title: '已添加', icon: 'success' })
      }
      this.setData({ showForm: false, editingId: null })
      await this.loadMembers()
    } catch (e) {
      let msg = '保存失败'
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
      title: '删除家人',
      content: '确定要删除该家人档案吗？历史订单不会受影响。',
      confirmText: '删除',
      confirmColor: '#e53935',
    })
    if (!res.confirm) return
    try {
      await deleteFamilyMember(id)
      wx.showToast({ title: '已删除', icon: 'success' })
      await this.loadMembers()
    } catch (err) {
      wx.showToast({ title: '删除失败', icon: 'none' })
    }
  },
})
