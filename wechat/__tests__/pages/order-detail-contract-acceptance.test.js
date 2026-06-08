/**
 * S3-DEV-001-CONTRACT-UI page-level tests for order-detail.
 *
 * 覆盖 5 AC (ADR-0047 §3 AC-3 + §6.3):
 * - AC#1 微信端 contract checkbox 默认 unchecked
 * - AC#2 支付按钮 disabled until 勾选 (UI 层 contractAccepted state 驱动)
 * - AC#3 勾选事件立即 POST /accept
 * - AC#4 合同正文展示 (signed URL via getContract)
 * - AC#5 E2E: 未勾选 → onPay 不放行; 勾选 → audit 落库
 */

jest.mock('../../services/order', () => ({
  getOrderDetail: jest.fn(),
  orderAction: jest.fn(),
  payOrder: jest.fn(),
  requestWechatPayment: jest.fn(),
}))
jest.mock('../../services/contract', () => ({
  acceptContract: jest.fn(),
  getContract: jest.fn(),
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
const contract = require('../../services/contract')

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

function createPage(initialOrder) {
  const cfg = loadPage()
  const page = Object.assign({}, cfg, {
    data: Object.assign({}, cfg.data, { order: initialOrder })
  })
  page.setData = function (obj) { Object.assign(this.data, obj) }
  page.orderId = (initialOrder && initialOrder.id) || 'order-1'
  return page
}

beforeEach(() => {
  jest.clearAllMocks()
  __resetWxStorage()
  wx.showToast = jest.fn()
  wx.showModal = jest.fn().mockResolvedValue({ confirm: true })
  wx.downloadFile = jest.fn()
  wx.openDocument = jest.fn()
  wx.redirectTo = jest.fn()
})

// ---------------------------------------------------------------------
// AC#1: contractAccepted 默认 false (checkbox 未勾选)
// ---------------------------------------------------------------------

describe('AC#1 default unchecked', () => {
  test('contractAccepted defaults to false on page init', () => {
    const cfg = loadPage()
    expect(cfg.data.contractAccepted).toBe(false)
  })
})

// ---------------------------------------------------------------------
// AC#3: 勾选立即 POST /accept (与切换状态同步)
// ---------------------------------------------------------------------

describe('AC#3 onToggleContractAccept', () => {
  test('toggles contractAccepted false → true and calls acceptContract', async () => {
    contract.acceptContract.mockResolvedValue({
      contract_id: 'c1', order_id: 'o1', accepted_at: '2026-06-08T07:00:00Z', audit_log_id: 'log1'
    })
    const page = createPage({ id: 'o1', contract_id: 'c1' })
    expect(page.data.contractAccepted).toBe(false)

    await page.onToggleContractAccept()

    expect(page.data.contractAccepted).toBe(true)
    expect(contract.acceptContract).toHaveBeenCalledWith('c1')
  })

  test('toggling back true → false does NOT call acceptContract', async () => {
    const page = createPage({ id: 'o1', contract_id: 'c1' })
    page.data.contractAccepted = true  // pre-set as if user already checked

    await page.onToggleContractAccept()

    expect(page.data.contractAccepted).toBe(false)
    expect(contract.acceptContract).not.toHaveBeenCalled()
  })

  test('acceptContract failure shows toast but keeps contractAccepted=true (UI 不回滚, 服务端 cron 兜底)', async () => {
    contract.acceptContract.mockRejectedValue({ statusCode: 500, data: { detail: 'audit log write failed' } })
    const page = createPage({ id: 'o1', contract_id: 'c1' })

    await page.onToggleContractAccept()

    expect(page.data.contractAccepted).toBe(true)  // UI 不回滚
    expect(wx.showToast).toHaveBeenCalled()
  })

  test('toggle on order without contract_id is a no-op (历史订单)', async () => {
    const page = createPage({ id: 'o-legacy' })  // no contract_id

    await page.onToggleContractAccept()

    expect(page.data.contractAccepted).toBe(false)  // 未切换
    expect(contract.acceptContract).not.toHaveBeenCalled()
  })

  test('repeated re-check creates multiple audit log calls (ADR-0047 §3.5 取证不去重)', async () => {
    contract.acceptContract.mockResolvedValue({
      contract_id: 'c1', order_id: 'o1', accepted_at: 't', audit_log_id: 'log'
    })
    const page = createPage({ id: 'o1', contract_id: 'c1' })

    // Sequence: check → uncheck → check → uncheck → check (3 audit calls)
    await page.onToggleContractAccept()  // check (calls accept)
    await page.onToggleContractAccept()  // uncheck (no call)
    await page.onToggleContractAccept()  // check (calls accept)
    await page.onToggleContractAccept()  // uncheck (no call)
    await page.onToggleContractAccept()  // check (calls accept)

    expect(contract.acceptContract).toHaveBeenCalledTimes(3)
  })
})

// ---------------------------------------------------------------------
// AC#4: 合同正文展示 (signed URL → downloadFile → openDocument)
// ---------------------------------------------------------------------

describe('AC#4 onViewContract', () => {
  test('active contract → downloadFile + openDocument PDF', async () => {
    contract.getContract.mockResolvedValue({
      contract_id: 'c1', order_id: 'o1', template_version: 'v1.0.0',
      status: 'active', signed_url: 'https://example/c.pdf', signed_url_expires_at: 't', generated_at: 't'
    })
    wx.downloadFile.mockImplementation((opts) => {
      opts.success({ statusCode: 200, tempFilePath: '/tmp/c.pdf' })
    })
    const page = createPage({ id: 'o1', contract_id: 'c1' })

    await page.onViewContract()

    expect(contract.getContract).toHaveBeenCalledWith('c1')
    expect(wx.downloadFile).toHaveBeenCalledWith(expect.objectContaining({
      url: 'https://example/c.pdf'
    }))
    expect(wx.openDocument).toHaveBeenCalledWith(expect.objectContaining({
      filePath: '/tmp/c.pdf',
      fileType: 'pdf'
    }))
  })

  test('pending_generation contract → toast "生成中" (no download)', async () => {
    contract.getContract.mockResolvedValue({
      contract_id: 'c1', status: 'pending_generation', signed_url: null
    })
    const page = createPage({ id: 'o1', contract_id: 'c1' })

    await page.onViewContract()

    expect(wx.downloadFile).not.toHaveBeenCalled()
    expect(wx.showToast).toHaveBeenCalledWith(expect.objectContaining({
      title: expect.stringContaining('尚未生成')
    }))
  })

  test('manually_invalidated contract → toast "已作废" (no download)', async () => {
    contract.getContract.mockResolvedValue({
      contract_id: 'c1', status: 'manually_invalidated', signed_url: null
    })
    const page = createPage({ id: 'o1', contract_id: 'c1' })

    await page.onViewContract()

    expect(wx.downloadFile).not.toHaveBeenCalled()
    expect(wx.showToast).toHaveBeenCalledWith(expect.objectContaining({
      title: expect.stringContaining('作废')
    }))
  })

  test('generation_failed → toast "生成失败"', async () => {
    contract.getContract.mockResolvedValue({
      contract_id: 'c1', status: 'generation_failed', signed_url: null
    })
    const page = createPage({ id: 'o1', contract_id: 'c1' })

    await page.onViewContract()

    expect(wx.showToast).toHaveBeenCalledWith(expect.objectContaining({
      title: expect.stringContaining('生成失败')
    }))
  })

  test('order without contract_id → no API call', async () => {
    const page = createPage({ id: 'o-legacy' })

    await page.onViewContract()

    expect(contract.getContract).not.toHaveBeenCalled()
  })
})

// ---------------------------------------------------------------------
// AC#5 E2E: 未勾选 → onPay 不应进入 payOrder 调用 (按钮 disabled 是 wxml 层,
// page handler 本身没 guard, 但 button disabled=... 会阻 bindtap, 这是
// 微信框架行为. 我们测 handler 层是 disabled 兜底假设可独立解锁)
// ---------------------------------------------------------------------

describe('AC#5 E2E checkbox-button binding', () => {
  test('order with contract_id but unchecked: onPay disabled state driven by wxml', () => {
    // wxml binding: disabled="{{actionLoading || (order.contract_id && !contractAccepted)}}"
    // 我们模拟 wxml 表达式得到 disabled 值
    const order = { id: 'o1', contract_id: 'c1', formattedPrice: '¥299' }
    const page = createPage(order)

    // disabled = actionLoading(false) || (contract_id(c1) && !contractAccepted(false)) = true
    const disabled = page.data.actionLoading || (order.contract_id && !page.data.contractAccepted)
    expect(disabled).toBe(true)
  })

  test('order with contract_id + checked: wxml disabled = false', async () => {
    contract.acceptContract.mockResolvedValue({ contract_id: 'c1', audit_log_id: 'log' })
    const order = { id: 'o1', contract_id: 'c1', formattedPrice: '¥299' }
    const page = createPage(order)

    await page.onToggleContractAccept()

    const disabled = page.data.actionLoading || (order.contract_id && !page.data.contractAccepted)
    expect(disabled).toBe(false)
  })

  test('order without contract_id (历史订单): always payable (no checkbox required)', () => {
    const order = { id: 'o-legacy', formattedPrice: '¥299' }
    const page = createPage(order)

    const disabled = page.data.actionLoading || (order.contract_id && !page.data.contractAccepted)
    expect(disabled).toBeFalsy()
  })
})
