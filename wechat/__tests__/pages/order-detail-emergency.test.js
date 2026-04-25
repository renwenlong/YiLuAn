// [F-03] order-detail emergency call interaction
jest.mock('../../services/order', () => ({
  getOrderDetail: jest.fn(),
  orderAction: jest.fn(),
  payOrder: jest.fn(),
  requestWechatPayment: jest.fn(),
}))
jest.mock('../../services/review', () => ({
  getOrderReview: jest.fn(),
}))
jest.mock('../../services/emergency', () => ({
  listEmergencyContacts: jest.fn(),
  getEmergencyHotline: jest.fn(),
  triggerEmergencyEvent: jest.fn(),
}))

global.Page = global.Page || jest.fn()

const emergency = require('../../services/emergency')

function loadPage() {
  let cfg
  const orig = global.Page
  global.Page = (c) => { cfg = c }
  jest.isolateModules(() => {
    require('../../pages/patient/order-detail/index')
  })
  global.Page = orig
  return cfg
}

function createPage(initial) {
  const cfg = loadPage()
  const page = Object.assign({}, cfg, { data: Object.assign({}, cfg.data, initial) })
  page.setData = function (obj) { Object.assign(this.data, obj) }
  page.orderId = 'order-1'
  return page
}

beforeEach(() => {
  jest.clearAllMocks()
  __resetWxStorage()
  wx.makePhoneCall = jest.fn()
  wx.navigateTo = jest.fn()
  wx.showToast = jest.fn()
})

describe('pages/patient/order-detail — F-03 emergency', () => {
  test('onEmergencyTap loads contacts and hotline', async () => {
    emergency.listEmergencyContacts.mockResolvedValue([
      { id: 'c1', name: 'A', phone: '13900139000', relationship: '朋友' },
    ])
    emergency.getEmergencyHotline.mockResolvedValue({ hotline: '4001234567' })
    const page = createPage()
    await page.onEmergencyTap()
    expect(page.data.showEmergency).toBe(true)
    expect(page.data.emergencyContacts).toHaveLength(1)
    expect(page.data.emergencyHotline).toBe('4001234567')
  })

  test('onCallContact triggers event and dials phone', async () => {
    emergency.triggerEmergencyEvent.mockResolvedValue({
      event: { id: 'e1', contact_type: 'contact' },
      phone_to_call: '13900139000',
    })
    const page = createPage({ showEmergency: true })
    await page.onCallContact({ currentTarget: { dataset: { id: 'c1' } } })
    expect(emergency.triggerEmergencyEvent).toHaveBeenCalledWith({
      order_id: 'order-1', contact_id: 'c1',
    })
    expect(wx.makePhoneCall).toHaveBeenCalledWith({ phoneNumber: '13900139000' })
    expect(page.data.showEmergency).toBe(false)
  })

  test('onCallHotline triggers hotline event', async () => {
    emergency.triggerEmergencyEvent.mockResolvedValue({
      event: { id: 'e2', contact_type: 'hotline' },
      phone_to_call: '4001234567',
    })
    const page = createPage({ showEmergency: true })
    await page.onCallHotline()
    expect(emergency.triggerEmergencyEvent).toHaveBeenCalledWith({
      order_id: 'order-1', hotline: true,
    })
    expect(wx.makePhoneCall).toHaveBeenCalledWith({ phoneNumber: '4001234567' })
  })

  test('onManageContacts navigates to contacts page', () => {
    const page = createPage({ showEmergency: true })
    page.onManageContacts()
    expect(wx.navigateTo).toHaveBeenCalledWith({
      url: '/pages/profile/emergency-contacts/index',
    })
    expect(page.data.showEmergency).toBe(false)
  })

  test('error from trigger shows toast and keeps modal', async () => {
    emergency.triggerEmergencyEvent.mockRejectedValue({
      data: { detail: { message: '失败' } },
    })
    const page = createPage({ showEmergency: true })
    await page.onCallHotline()
    expect(wx.showToast).toHaveBeenCalledWith(expect.objectContaining({ title: '失败' }))
    expect(wx.makePhoneCall).not.toHaveBeenCalled()
  })
})
