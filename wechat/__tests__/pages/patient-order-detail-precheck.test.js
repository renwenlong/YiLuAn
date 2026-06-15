/**
 * Integration tests for patient/order-detail precheck cert card wiring
 * (S3-DEV-003-TRUST-UI-WX AC#4 + AC#5).
 *
 * Cover:
 * - onLoad → _loadPrecheck → setData certStatus (3 状态)
 * - WS event 'precheck.status.updated' 触发 _loadPrecheck 重拉
 * - WS event 'precheck.all_ready' / 'precheck.blocked' 同样触发重拉
 * - onUnload → precheckWs.disconnect()
 * - certStatus null 时 cert-card 不渲染 (path through wxml 由 cert-card test 验证;
 *   这里只断 page data shape)
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
jest.mock('../../services/followupReminder', () => ({
  createFollowupReminder: jest.fn(),
}))
jest.mock('../../services/emergency', () => ({
  listEmergencyContacts: jest.fn(),
  getEmergencyHotline: jest.fn(),
  triggerEmergencyEvent: jest.fn(),
}))
jest.mock('../../services/precheck', () => ({
  getOrderPrecheckStatus: jest.fn(),
}))
jest.mock('../../services/precheckWs', () => ({
  connect: jest.fn(),
  disconnect: jest.fn(),
}))
jest.mock('../../store/index', () => ({
  getState: jest.fn(() => ({})),
  setState: jest.fn(),
  subscribe: jest.fn(),
}))

const orderService = require('../../services/order')
const reviewService = require('../../services/review')
const precheckService = require('../../services/precheck')
const precheckWs = require('../../services/precheckWs')

var pageConfig
;(function () {
  var configs = []
  global.Page = function (cfg) { configs.push(cfg) }
  jest.isolateModules(function () {
    require('../../pages/patient/order-detail/index')
  })
  pageConfig = configs[0]
})()

function createPage() {
  var page = Object.assign({}, pageConfig)
  // Reset data and copy methods.
  page.data = Object.assign({}, pageConfig.data)
  page.setData = jest.fn(function (obj) { Object.assign(this.data, obj) })
  return page
}

beforeEach(function () {
  jest.clearAllMocks()
  __resetWxStorage()
  orderService.getOrderDetail.mockResolvedValue({
    id: 'o1',
    status: 'accepted',
    payment_status: 'unpaid',
    service_type: 'errand',
    appointment_date: '2026-07-01',
    appointment_time: '09:00',
    companion_name: '陪诊师',
    expires_at: null,
  })
  reviewService.getOrderReview.mockResolvedValue(null)
})

describe('patient/order-detail S3-DEV-003-TRUST-UI-WX', () => {

  test('onLoad triggers _loadPrecheck + _connectPrecheckWs', async function () {
    precheckService.getOrderPrecheckStatus.mockResolvedValue({
      companion_cert_status: {
        ready: true,
        companion_cert_pseudonym_name: '陈师傅',
        companion_cert_work_id: 'PC0042',
        companion_cert_qualifications: ['康复治疗师'],
        companion_cert_verified_at: '2026-05-10T12:00:00Z',
      },
    })
    var page = createPage()
    page.onLoad({ id: 'o1' })
    // wait for async _loadPrecheck.
    await new Promise(function (r) { setImmediate(r) })

    expect(precheckService.getOrderPrecheckStatus).toHaveBeenCalledWith('o1')
    expect(precheckWs.connect).toHaveBeenCalledTimes(1)
    var wsArgs = precheckWs.connect.mock.calls[0][0]
    expect(wsArgs.orderId).toBe('o1')
    expect(typeof wsArgs.onEvent).toBe('function')
    expect(page.data.certStatus).toEqual({
      ready: true,
      companion_cert_pseudonym_name: '陈师傅',
      companion_cert_work_id: 'PC0042',
      companion_cert_qualifications: ['康复治疗师'],
      companion_cert_verified_at: '2026-05-10T12:00:00Z',
    })
  })

  test('AC#5 verified state: ready=true sets data.certStatus.ready=true', async function () {
    precheckService.getOrderPrecheckStatus.mockResolvedValue({
      companion_cert_status: { ready: true, companion_cert_work_id: 'PC0001' },
    })
    var page = createPage()
    await page._loadPrecheck.call(Object.assign(page, { orderId: 'o1' }))
    expect(page.data.certStatus.ready).toBe(true)
  })

  test('AC#5 pending_resubmit state: ready=false + work_id 保留', async function () {
    precheckService.getOrderPrecheckStatus.mockResolvedValue({
      companion_cert_status: {
        ready: false,
        companion_cert_work_id: 'PC0042',
        companion_cert_pseudonym_name: '陈师傅',
      },
    })
    var page = createPage()
    await page._loadPrecheck.call(Object.assign(page, { orderId: 'o1' }))
    expect(page.data.certStatus.ready).toBe(false)
    expect(page.data.certStatus.companion_cert_work_id).toBe('PC0042')
  })

  test('AC#5 unverified state: ready=false + 字段空', async function () {
    precheckService.getOrderPrecheckStatus.mockResolvedValue({
      companion_cert_status: { ready: false },
    })
    var page = createPage()
    await page._loadPrecheck.call(Object.assign(page, { orderId: 'o1' }))
    expect(page.data.certStatus).toEqual({ ready: false })
  })

  test('AC#4: WS event precheck.status.updated 触发 _loadPrecheck 重拉', async function () {
    // 1st call returns ready=false, 2nd call (after WS event) returns ready=true.
    precheckService.getOrderPrecheckStatus
      .mockResolvedValueOnce({ companion_cert_status: { ready: false } })
      .mockResolvedValueOnce({
        companion_cert_status: {
          ready: true,
          companion_cert_work_id: 'PC0042',
        }
      })
    var page = createPage()
    page.onLoad({ id: 'o1' })
    await new Promise(function (r) { setImmediate(r) })
    expect(page.data.certStatus.ready).toBe(false)

    // Now simulate WS event.
    var wsArgs = precheckWs.connect.mock.calls[0][0]
    wsArgs.onEvent({ event: 'precheck.status.updated', card: 'cert' })
    await new Promise(function (r) { setImmediate(r) })
    expect(page.data.certStatus.ready).toBe(true)
    expect(page.data.certStatus.companion_cert_work_id).toBe('PC0042')
    expect(precheckService.getOrderPrecheckStatus).toHaveBeenCalledTimes(2)
  })

  test('AC#4: WS event precheck.all_ready 也触发重拉', async function () {
    precheckService.getOrderPrecheckStatus
      .mockResolvedValueOnce({ companion_cert_status: { ready: false } })
      .mockResolvedValueOnce({ companion_cert_status: { ready: true } })
    var page = createPage()
    page.onLoad({ id: 'o1' })
    await new Promise(function (r) { setImmediate(r) })
    var wsArgs = precheckWs.connect.mock.calls[0][0]
    wsArgs.onEvent({ event: 'precheck.all_ready' })
    await new Promise(function (r) { setImmediate(r) })
    expect(precheckService.getOrderPrecheckStatus).toHaveBeenCalledTimes(2)
  })

  test('AC#4: WS event precheck.blocked 也触发重拉', async function () {
    precheckService.getOrderPrecheckStatus
      .mockResolvedValueOnce({ companion_cert_status: { ready: true } })
      .mockResolvedValueOnce({ companion_cert_status: { ready: false } })
    var page = createPage()
    page.onLoad({ id: 'o1' })
    await new Promise(function (r) { setImmediate(r) })
    var wsArgs = precheckWs.connect.mock.calls[0][0]
    wsArgs.onEvent({ event: 'precheck.blocked' })
    await new Promise(function (r) { setImmediate(r) })
    expect(precheckService.getOrderPrecheckStatus).toHaveBeenCalledTimes(2)
  })

  test('WS unknown event 不触发重拉', async function () {
    precheckService.getOrderPrecheckStatus
      .mockResolvedValueOnce({ companion_cert_status: { ready: true } })
    var page = createPage()
    page.onLoad({ id: 'o1' })
    await new Promise(function (r) { setImmediate(r) })
    var wsArgs = precheckWs.connect.mock.calls[0][0]
    wsArgs.onEvent({ event: 'some.other.event' })
    wsArgs.onEvent(null)  // null payload safety
    await new Promise(function (r) { setImmediate(r) })
    expect(precheckService.getOrderPrecheckStatus).toHaveBeenCalledTimes(1)
  })

  test('precheck 拉失败 silent 不阻主流程, certStatus 保持 null', async function () {
    precheckService.getOrderPrecheckStatus.mockRejectedValue({
      data: { detail: 'Not Found' },
      statusCode: 404,
    })
    var page = createPage()
    page.onLoad({ id: 'o1' })
    await new Promise(function (r) { setImmediate(r) })
    expect(page.data.certStatus).toBeNull()
  })

  test('onUnload triggers precheckWs.disconnect', function () {
    var page = createPage()
    page.orderId = 'o1'
    page.onUnload()
    expect(precheckWs.disconnect).toHaveBeenCalledTimes(1)
  })

  // -------------------------------------------------------------------------
  // S3-DEV-003-TRUST-UI-WX-POLLING-FALLBACK: page-level state integration
  //
  // 跨端对齐 iOS PrecheckViewModel.isPollingFallback @Published — page setData
  // 同路径 使 wxml `wx:if="{{isPollingFallback}}"` 企业提示 UI 可现.
  //
  // AC#5: page-level state (如 isPollingFallback) 反映 polling 激活,
  //       UI 可显示 fallback 提示.
  // -------------------------------------------------------------------------

  test('AC#5 initial state: isPollingFallback = false (data shape)', async function () {
    precheckService.getOrderPrecheckStatus.mockResolvedValue({
      companion_cert_status: { ready: false },
    })
    var page = createPage()
    expect(page.data.isPollingFallback).toBe(false)
  })

  test('AC#5: onConnectionState({isPollingFallback:true}) → page.setData 反映', async function () {
    precheckService.getOrderPrecheckStatus.mockResolvedValue({
      companion_cert_status: { ready: false },
    })
    var page = createPage()
    page.onLoad({ id: 'o1' })
    await new Promise(function (r) { setImmediate(r) })

    var wsArgs = precheckWs.connect.mock.calls[0][0]
    expect(typeof wsArgs.onConnectionState).toBe('function')
    expect(typeof wsArgs.onShouldRefresh).toBe('function')

    // Simulate WS 断 → precheckWs 上报 polling started.
    wsArgs.onConnectionState({
      isPollingFallback: true,
      reason: 'ws_closed_code_1006',
    })
    expect(page.data.isPollingFallback).toBe(true)

    // Simulate WS 重连成功 → precheckWs 上报 polling stopped.
    wsArgs.onConnectionState({
      isPollingFallback: false,
      reason: 'ws_authenticated',
    })
    expect(page.data.isPollingFallback).toBe(false)
  })

  test('AC#5: permanentFailure (4001) → isPollingFallback 不 设 true (不误提示轮询)', async function () {
    precheckService.getOrderPrecheckStatus.mockResolvedValue({
      companion_cert_status: { ready: false },
    })
    var page = createPage()
    page.onLoad({ id: 'o1' })
    await new Promise(function (r) { setImmediate(r) })

    var wsArgs = precheckWs.connect.mock.calls[0][0]

    // 永久失败 — precheckWs 上报 permanentFailure, page 不 显示 polling 提示.
    wsArgs.onConnectionState({
      isPollingFallback: false,
      permanentFailure: true,
      code: 4001,
      reason: 'invalid token',
    })
    expect(page.data.isPollingFallback).toBe(false)
  })

  test('AC#4: onShouldRefresh 回调 = _loadPrecheck (polling tick 复用同路径)', async function () {
    precheckService.getOrderPrecheckStatus
      .mockResolvedValueOnce({ companion_cert_status: { ready: false } })
      .mockResolvedValueOnce({
        companion_cert_status: { ready: true, companion_cert_work_id: 'PC9999' },
      })
    var page = createPage()
    page.onLoad({ id: 'o1' })
    await new Promise(function (r) { setImmediate(r) })
    expect(page.data.certStatus.ready).toBe(false)

    var wsArgs = precheckWs.connect.mock.calls[0][0]
    // Polling tick 调 onShouldRefresh — 应 trigger 同一 _loadPrecheck HTTP 路径.
    await wsArgs.onShouldRefresh()
    expect(page.data.certStatus.ready).toBe(true)
    expect(page.data.certStatus.companion_cert_work_id).toBe('PC9999')
    expect(precheckService.getOrderPrecheckStatus).toHaveBeenCalledTimes(2)
  })
})
