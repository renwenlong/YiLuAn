// [F-03] Emergency contacts management page
const {
  listEmergencyContacts,
  createEmergencyContact,
  updateEmergencyContact,
  deleteEmergencyContact,
} = require('../../../services/emergency')

const MAX_CONTACTS = 3

Page({
  data: {
    contacts: [],
    loading: true,
    showForm: false,
    editingId: null,
    form: { name: '', phone: '', relationship: '' },
    canAdd: true,
  },

  onLoad() {
    this.loadContacts()
  },

  onShow() {
    if (!this.data.loading) this.loadContacts()
  },

  async loadContacts() {
    this.setData({ loading: true })
    try {
      const contacts = await listEmergencyContacts()
      this.setData({
        contacts,
        canAdd: contacts.length < MAX_CONTACTS,
      })
    } catch (e) {
      wx.showToast({ title: '加载失败', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  onAddTap() {
    if (!this.data.canAdd) {
      wx.showToast({ title: `最多只能添加${MAX_CONTACTS}个联系人`, icon: 'none' })
      return
    }
    this.setData({
      showForm: true,
      editingId: null,
      form: { name: '', phone: '', relationship: '' },
    })
  },

  onEditTap(e) {
    const { id } = e.currentTarget.dataset
    const contact = this.data.contacts.find(c => c.id === id)
    if (!contact) return
    this.setData({
      showForm: true,
      editingId: id,
      form: {
        name: contact.name,
        phone: contact.phone,
        relationship: contact.relationship,
      },
    })
  },

  onCancelForm() {
    this.setData({ showForm: false, editingId: null })
  },

  onNameInput(e) {
    this.setData({ 'form.name': e.detail.value })
  },
  onPhoneInput(e) {
    this.setData({ 'form.phone': e.detail.value })
  },
  onRelationshipInput(e) {
    this.setData({ 'form.relationship': e.detail.value })
  },

  _validate() {
    const { name, phone, relationship } = this.data.form
    if (!name || !name.trim()) return '请填写姓名'
    if (!/^1[3-9]\d{9}$/.test(phone)) return '请填写正确手机号'
    if (!relationship || !relationship.trim()) return '请填写关系'
    return null
  },

  async onSubmit() {
    const err = this._validate()
    if (err) {
      wx.showToast({ title: err, icon: 'none' })
      return
    }
    const { name, phone, relationship } = this.data.form
    const payload = {
      name: name.trim(),
      phone: phone.trim(),
      relationship: relationship.trim(),
    }
    try {
      if (this.data.editingId) {
        await updateEmergencyContact(this.data.editingId, payload)
        wx.showToast({ title: '已更新', icon: 'success' })
      } else {
        await createEmergencyContact(payload)
        wx.showToast({ title: '已添加', icon: 'success' })
      }
      this.setData({ showForm: false, editingId: null })
      await this.loadContacts()
    } catch (e) {
      var msg = '保存失败'
      if (e && e.data && e.data.detail) {
        var d = e.data.detail
        msg = (d && d.message) || (typeof d === 'string' ? d : msg)
      }
      wx.showToast({ title: msg, icon: 'none' })
    }
  },

  async onDeleteTap(e) {
    const { id } = e.currentTarget.dataset
    const res = await wx.showModal({
      title: '删除联系人',
      content: '确定要删除该紧急联系人吗？',
      confirmText: '删除',
      confirmColor: '#e53935',
    })
    if (!res.confirm) return
    try {
      await deleteEmergencyContact(id)
      wx.showToast({ title: '已删除', icon: 'success' })
      await this.loadContacts()
    } catch (err) {
      wx.showToast({ title: '删除失败', icon: 'none' })
    }
  },
})
