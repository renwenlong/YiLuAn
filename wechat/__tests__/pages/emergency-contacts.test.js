// [F-03] emergency contacts page
jest.mock('../../services/emergency', () => ({
  listEmergencyContacts: jest.fn(),
  createEmergencyContact: jest.fn(),
  updateEmergencyContact: jest.fn(),
  deleteEmergencyContact: jest.fn(),
}))

global.Page = global.Page || jest.fn()

const emergencyService = require('../../services/emergency')

function loadPageConfig() {
  let cfg
  const orig = global.Page
  global.Page = (c) => { cfg = c }
  jest.isolateModules(() => {
    require('../../pages/profile/emergency-contacts/index')
  })
  global.Page = orig
  return cfg
}

function createPage(initial) {
  const cfg = loadPageConfig()
  const page = Object.assign({}, cfg, { data: Object.assign({}, cfg.data, initial) })
  page.setData = function (obj) {
    Object.keys(obj).forEach((k) => {
      if (k.indexOf('.') > -1) {
        const [a, b] = k.split('.')
        this.data[a] = Object.assign({}, this.data[a], { [b]: obj[k] })
      } else {
        this.data[k] = obj[k]
      }
    })
  }
  return page
}

beforeEach(() => {
  jest.clearAllMocks()
  __resetWxStorage()
  wx.setStorageSync('yiluan_access_token', 'test_token')
  wx.showModal = jest.fn(() => Promise.resolve({ confirm: true }))
  wx.showToast = jest.fn()
})

describe('pages/profile/emergency-contacts', () => {
  test('loads contacts and computes canAdd', async () => {
    emergencyService.listEmergencyContacts.mockResolvedValue([
      { id: 'c1', name: 'A', phone: '13900139000', relationship: '朋友' },
    ])
    const page = createPage()
    await page.loadContacts()
    expect(page.data.contacts).toHaveLength(1)
    expect(page.data.canAdd).toBe(true)
  })

  test('canAdd false when 3 contacts exist', async () => {
    emergencyService.listEmergencyContacts.mockResolvedValue([
      { id: 'c1' }, { id: 'c2' }, { id: 'c3' },
    ])
    const page = createPage()
    await page.loadContacts()
    expect(page.data.canAdd).toBe(false)
  })

  test('onAddTap opens form when canAdd', () => {
    const page = createPage({ canAdd: true })
    page.onAddTap()
    expect(page.data.showForm).toBe(true)
    expect(page.data.editingId).toBe(null)
  })

  test('onAddTap blocked when canAdd false', () => {
    const page = createPage({ canAdd: false })
    page.onAddTap()
    expect(page.data.showForm).toBeFalsy()
    expect(wx.showToast).toHaveBeenCalled()
  })

  test('onEditTap loads contact into form', () => {
    const page = createPage({
      contacts: [{ id: 'c1', name: 'A', phone: '13900139000', relationship: '朋友' }],
    })
    page.onEditTap({ currentTarget: { dataset: { id: 'c1' } } })
    expect(page.data.showForm).toBe(true)
    expect(page.data.editingId).toBe('c1')
    expect(page.data.form.name).toBe('A')
  })

  test('onSubmit validates phone', async () => {
    const page = createPage({
      form: { name: 'A', phone: 'abc', relationship: '朋友' },
    })
    await page.onSubmit()
    expect(emergencyService.createEmergencyContact).not.toHaveBeenCalled()
    expect(wx.showToast).toHaveBeenCalledWith(expect.objectContaining({ title: '请填写正确手机号' }))
  })

  test('onSubmit creates new contact', async () => {
    emergencyService.createEmergencyContact.mockResolvedValue({ id: 'c1' })
    emergencyService.listEmergencyContacts.mockResolvedValue([{ id: 'c1' }])
    const page = createPage({
      form: { name: 'A', phone: '13900139000', relationship: '朋友' },
      editingId: null,
    })
    await page.onSubmit()
    expect(emergencyService.createEmergencyContact).toHaveBeenCalledWith({
      name: 'A', phone: '13900139000', relationship: '朋友',
    })
    expect(page.data.showForm).toBe(false)
  })

  test('onSubmit updates existing contact', async () => {
    emergencyService.updateEmergencyContact.mockResolvedValue({ id: 'c1' })
    emergencyService.listEmergencyContacts.mockResolvedValue([])
    const page = createPage({
      form: { name: 'B', phone: '13900139001', relationship: '朋友' },
      editingId: 'c1',
    })
    await page.onSubmit()
    expect(emergencyService.updateEmergencyContact).toHaveBeenCalledWith(
      'c1',
      { name: 'B', phone: '13900139001', relationship: '朋友' }
    )
  })

  test('onDeleteTap calls service after confirm', async () => {
    emergencyService.deleteEmergencyContact.mockResolvedValue()
    emergencyService.listEmergencyContacts.mockResolvedValue([])
    const page = createPage()
    await page.onDeleteTap({ currentTarget: { dataset: { id: 'c1' } } })
    expect(emergencyService.deleteEmergencyContact).toHaveBeenCalledWith('c1')
  })
})
