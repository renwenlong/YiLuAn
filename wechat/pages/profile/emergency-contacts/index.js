// [F-03] Emergency contacts management page
const {
  listEmergencyContacts,
  createEmergencyContact,
  updateEmergencyContact,
  deleteEmergencyContact,
} = require('../../../services/emergency')

const MAX_CONTACTS = 3
const i18n = require('../../../utils/i18n')
const i18nBehavior = require('../../../behaviors/i18n')

Page({
  behaviors: [i18nBehavior],
  data: {
    i18nScopes: ['common', 'emergencyContacts'],
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
      wx.showToast({ title: i18n.t('emergencyContacts.loadFailed'), icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  onAddTap() {
    if (!this.data.canAdd) {
      wx.showToast({ title: i18n.t('emergencyContacts.maxLimit', { count: MAX_CONTACTS }), icon: 'none' })
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
    if (!name || !name.trim()) return i18n.t('emergencyContacts.fillName')
    if (!/^1[3-9]\d{9}$/.test(phone)) return i18n.t('emergencyContacts.fillValidPhone')
    if (!relationship || !relationship.trim()) return i18n.t('emergencyContacts.fillRelation')
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
        wx.showToast({ title: i18n.t('emergencyContacts.updated'), icon: 'success' })
      } else {
        await createEmergencyContact(payload)
        wx.showToast({ title: i18n.t('emergencyContacts.added'), icon: 'success' })
      }
      this.setData({ showForm: false, editingId: null })
      await this.loadContacts()
    } catch (e) {
      var msg = i18n.t('emergencyContacts.saveFailed')
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
      title: i18n.t('emergencyContacts.deleteTitle'),
      content: i18n.t('emergencyContacts.deleteConfirm'),
      confirmText: i18n.t('emergencyContacts.delete'),
      confirmColor: '#e53935',
    })
    if (!res.confirm) return
    try {
      await deleteEmergencyContact(id)
      wx.showToast({ title: i18n.t('emergencyContacts.deleted'), icon: 'success' })
      await this.loadContacts()
    } catch (err) {
      wx.showToast({ title: i18n.t('emergencyContacts.deleteFailed'), icon: 'none' })
    }
  },
})
