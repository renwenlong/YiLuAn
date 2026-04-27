// AI-9: order-detail actionLoading lock
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

const order = require('../../services/order')

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
  wx.showToast = jest.fn()
  wx.showModal = jest.fn().mockResolvedValue({ confirm: true })
  wx.makePhoneCall = jest.fn()
  wx.navigateTo = jest.fn()
  wx.redirectTo = jest.fn()
})

describe('pages/patient/order-detail — AI-9 actionLoading', () => {
  test('actionLoading defaults to false', () => {
    const page = createPage()
    expect(page.data.actionLoading).toBe(false)
  })

  test('onConfirmStart toggles actionLoading true → false (success)', async () => {
    let resolveAction
    order.orderAction.mockReturnValue(new Promise((r) => { resolveAction = r }))
    const page = createPage({
      order: { status: 'accepted' },
    })
    page.loadOrder = jest.fn().mockResolvedValue()

    const promise = page.onConfirmStart()
    // 微任务跑过 wx.showModal + setData
    await Promise.resolve()
    await Promise.resolve()
    expect(page.data.actionLoading).toBe(true)

    resolveAction({})
    await promise
    expect(page.data.actionLoading).toBe(false)
    expect(wx.showToast).toHaveBeenCalledWith(
      expect.objectContaining({ title: '服务已开始', icon: 'success' })
    )
  })

  test('onCancel toggles actionLoading false on error too (try/finally)', async () => {
    order.orderAction.mockRejectedValue(new Error('net'))
    const page = createPage({
      order: { status: 'created', payment_status: 'unpaid' },
    })
    page.loadOrder = jest.fn().mockResolvedValue()

    await page.onCancel()
    expect(page.data.actionLoading).toBe(false)
    expect(wx.showToast).toHaveBeenCalledWith(
      expect.objectContaining({ title: '操作失败' })
    )
  })

  test('onCancel re-entry while actionLoading=true is a no-op', async () => {
    let resolveAction
    order.orderAction.mockReturnValue(new Promise((r) => { resolveAction = r }))
    const page = createPage({
      order: { status: 'created', payment_status: 'unpaid' },
    })
    page.loadOrder = jest.fn().mockResolvedValue()

    const first = page.onCancel()
    // 让 first 进入 actionLoading=true
    await Promise.resolve()
    await Promise.resolve()
    expect(page.data.actionLoading).toBe(true)

    // 第二次点击：再走一次 wx.showModal，但内部应在锁判断处 return
    await page.onCancel()
    expect(order.orderAction).toHaveBeenCalledTimes(1)

    resolveAction({})
    await first
    expect(page.data.actionLoading).toBe(false)
  })

  test('onCancelInProgress also wraps actionLoading', async () => {
    order.orderAction.mockResolvedValue({})
    const page = createPage({
      order: { status: 'in_progress' },
    })
    page.loadOrder = jest.fn().mockResolvedValue()

    await page.onCancelInProgress()
    expect(order.orderAction).toHaveBeenCalledWith('order-1', 'cancel')
    expect(page.data.actionLoading).toBe(false)
  })

  test('skeleton condition: loading && !order leaves actionLoading untouched', () => {
    const page = createPage({ loading: true, order: null })
    expect(page.data.loading).toBe(true)
    expect(page.data.order).toBeNull()
    expect(page.data.actionLoading).toBe(false)
  })
})
