/**
 * Unit tests for services/precheckWs (S3-DEV-003-TRUST-UI-WX).
 *
 * Cover:
 * - connect() builds URL /api/v1/ws/v1/orders/{order_id}/precheck (含 order_id 段)
 * - connect() 不在 URL 里塞 token (鉴权走 first-frame auth)
 * - authPayload returns { type: 'auth', token: ... } 用当前 access_token
 * - disconnect() clears instance + callback
 * - connect skipped 当 no orderId or no token (defensive)
 * - onEvent callback 收 message
 */
jest.mock('../../core/ws-base', function () {
  // Mock WSBase ctor with jest.fn() so we get mock.instances / mock.calls.
  const WSBase = jest.fn().mockImplementation(function (options) {
    this.options = options
    this._handlers = {}
    this.connect = jest.fn()
    this.disconnect = jest.fn()
    this.on = jest.fn(function (event, fn) {
      this._handlers[event] = fn
    })
  })
  return { WSBase: WSBase }
})

const precheckWs = require('../../services/precheckWs')
const config = require('../../config/index')

beforeEach(() => {
  jest.clearAllMocks()
  __resetWxStorage()
  // disconnect any leftover instance (test isolation)
  precheckWs.disconnect()
})

describe('services/precheckWs', () => {
  test('connect builds WS URL with order_id, no token in URL', () => {
    wx.setStorageSync('yiluan_access_token', 'tok_abc')
    precheckWs.connect({ orderId: 'order-uuid-1', onEvent: jest.fn() })
    // First call: WSBase ctor created instance (mocked).
    // 然后 inst.connect(url) 被调.
    const { WSBase } = require('../../core/ws-base')
    const inst = WSBase.mock.instances[0]
    expect(inst.connect).toHaveBeenCalledTimes(1)
    const url = inst.connect.mock.calls[0][0]
    expect(url).toBe(config.WS_BASE_URL + '/api/v1/ws/v1/orders/order-uuid-1/precheck')
    expect(url).not.toContain('token=')
    expect(url).not.toContain('tok_abc')
  })

  test('authPayload returns { type: auth, token } 用当前 access_token', () => {
    wx.setStorageSync('yiluan_access_token', 'tok_xyz')
    precheckWs.connect({ orderId: 'o1', onEvent: jest.fn() })
    const { WSBase } = require('../../core/ws-base')
    const ctorOpts = WSBase.mock.calls[0][0]
    const payload = ctorOpts.authPayload()
    expect(payload).toEqual({ type: 'auth', token: 'tok_xyz' })
  })

  test('authPayload returns null when no token', () => {
    // Even after a previous test got an instance, authPayload reads fresh.
    wx.setStorageSync('yiluan_access_token', 'tok_x')
    precheckWs.connect({ orderId: 'o1', onEvent: jest.fn() })
    wx.removeStorageSync('yiluan_access_token')
    const { WSBase } = require('../../core/ws-base')
    const ctorOpts = WSBase.mock.calls[0][0]
    const payload = ctorOpts.authPayload()
    expect(payload).toBeNull()
  })

  test('connect 跳过 当 no orderId', () => {
    wx.setStorageSync('yiluan_access_token', 'tok_x')
    precheckWs.connect({ onEvent: jest.fn() })
    const { WSBase } = require('../../core/ws-base')
    expect(WSBase.mock.instances.length).toBe(0)
  })

  test('connect 跳过 当 no access token', () => {
    // Note: 我们检 token 在 connect, instance 不建.
    // wx storage empty.
    precheckWs.connect({ orderId: 'o1', onEvent: jest.fn() })
    const { WSBase } = require('../../core/ws-base')
    expect(WSBase.mock.instances.length).toBe(0)
  })

  test('onEvent callback 收到 message event 数据', () => {
    wx.setStorageSync('yiluan_access_token', 'tok_x')
    const onEvent = jest.fn()
    precheckWs.connect({ orderId: 'o1', onEvent: onEvent })
    const { WSBase } = require('../../core/ws-base')
    const inst = WSBase.mock.instances[0]
    // Simulate WSBase emitting message:
    const messageHandler = inst._handlers['message']
    expect(messageHandler).toBeDefined()
    messageHandler({ event: 'precheck.status.updated', card: 'cert' })
    expect(onEvent).toHaveBeenCalledWith({
      event: 'precheck.status.updated',
      card: 'cert',
    })
  })

  test('disconnect clears instance', () => {
    wx.setStorageSync('yiluan_access_token', 'tok_x')
    precheckWs.connect({ orderId: 'o1', onEvent: jest.fn() })
    const { WSBase } = require('../../core/ws-base')
    const inst = WSBase.mock.instances[0]
    precheckWs.disconnect()
    expect(inst.disconnect).toHaveBeenCalledTimes(1)
    // 第二次 connect 应建新 instance (旧的 disconnect 清了 _instance)
    precheckWs.connect({ orderId: 'o2', onEvent: jest.fn() })
    expect(WSBase.mock.instances.length).toBe(2)
  })
})

// ---------------------------------------------------------------------------
// S3-DEV-003-TRUST-UI-WX-POLLING-FALLBACK: Polling fallback tests
//
// 跨端对齐 iOS PrecheckViewModel.startPolling / stopPolling / isPollingFallback.
//
// Cover 5 AC:
//   AC#1: startPolling / stopPolling 函数 (30s 周期)
//   AC#2: WS 断时 (idle/network/unknown) auto-trigger startPolling
//   AC#3: WS 重连成功 auto-stopPolling 互斥 ('authenticated' event)
//   AC#4: polling 调 onShouldRefresh 回调 (page 内 _loadPrecheck 推 HTTP)
//   AC#5: onConnectionState 回调上报 isPollingFallback (page setData 用)
//
// 另加 1 个跨端对齐 test: 永久失败 code (4001/4003/4004/4011) 不 启 polling.
// ---------------------------------------------------------------------------

describe('services/precheckWs polling fallback', () => {
  beforeEach(() => {
    jest.useFakeTimers()
    wx.setStorageSync('yiluan_access_token', 'tok_x')
  })

  afterEach(() => {
    // Stop polling + clear instance before next test (test isolation).
    precheckWs.disconnect()
    jest.useRealTimers()
  })

  test('POLLING_INTERVAL_MS exported = 30000 (跨端对齐 iOS 30s)', () => {
    expect(precheckWs.POLLING_INTERVAL_MS).toBe(30000)
  })

  test('PERMANENT_FAILURE_CODES exported = [4001, 4003, 4004, 4011] (跨端对齐 iOS)', () => {
    expect(precheckWs.PERMANENT_FAILURE_CODES).toEqual([4001, 4003, 4004, 4011])
  })

  test('AC#2: WS close (临时失败 code 1006 network) 启 polling', () => {
    const onConnectionState = jest.fn()
    const onShouldRefresh = jest.fn().mockResolvedValue(undefined)
    precheckWs.connect({
      orderId: 'o1',
      onEvent: jest.fn(),
      onShouldRefresh: onShouldRefresh,
      onConnectionState: onConnectionState,
    })
    const { WSBase } = require('../../core/ws-base')
    const inst = WSBase.mock.instances[0]
    const closeHandler = inst._handlers['close']
    expect(closeHandler).toBeDefined()

    // Simulate 临时失败 (网络断, code 1006 abnormal closure).
    closeHandler({ code: 1006, reason: 'network' })

    // onConnectionState 上报 isPollingFallback=true.
    expect(onConnectionState).toHaveBeenCalledWith({
      isPollingFallback: true,
      reason: 'ws_closed_code_1006',
    })
    expect(precheckWs._isPollingActiveForTests()).toBe(true)
  })

  test('AC#2: WS close (idle/unknown code undefined) 启 polling', () => {
    const onConnectionState = jest.fn()
    precheckWs.connect({
      orderId: 'o1',
      onEvent: jest.fn(),
      onConnectionState: onConnectionState,
    })
    const { WSBase } = require('../../core/ws-base')
    const inst = WSBase.mock.instances[0]
    const closeHandler = inst._handlers['close']

    // 未知 code (类 iOS "unknown" 分支).
    closeHandler({ code: undefined, reason: null })

    expect(onConnectionState).toHaveBeenCalledWith({
      isPollingFallback: true,
      reason: 'ws_closed_code_unknown',
    })
  })

  test('AC#2 变体: 永久失败 code 4001 (鉴权失败) NOT 启 polling, 上报 permanentFailure', () => {
    const onConnectionState = jest.fn()
    precheckWs.connect({
      orderId: 'o1',
      onEvent: jest.fn(),
      onConnectionState: onConnectionState,
    })
    const { WSBase } = require('../../core/ws-base')
    const inst = WSBase.mock.instances[0]
    const closeHandler = inst._handlers['close']

    closeHandler({ code: 4001, reason: 'invalid token' })

    // Polling NOT started.
    expect(precheckWs._isPollingActiveForTests()).toBe(false)
    // 上报 permanentFailure=true (page 查 该字段 不设 isPollingFallback).
    expect(onConnectionState).toHaveBeenCalledWith({
      isPollingFallback: false,
      permanentFailure: true,
      code: 4001,
      reason: 'invalid token',
    })
  })

  test('AC#2 变体: 永久失败 code 4011 (ABAC 拒) NOT 启 polling', () => {
    const onConnectionState = jest.fn()
    precheckWs.connect({
      orderId: 'o1',
      onEvent: jest.fn(),
      onConnectionState: onConnectionState,
    })
    const { WSBase } = require('../../core/ws-base')
    const inst = WSBase.mock.instances[0]

    inst._handlers['close']({ code: 4011, reason: 'forbidden' })

    expect(precheckWs._isPollingActiveForTests()).toBe(false)
    expect(onConnectionState).toHaveBeenCalledWith(
      expect.objectContaining({ permanentFailure: true, code: 4011 })
    )
  })

  test('AC#3: 收到 ws-base authenticated event 后 停 polling 互斥', () => {
    const onConnectionState = jest.fn()
    precheckWs.connect({
      orderId: 'o1',
      onEvent: jest.fn(),
      onConnectionState: onConnectionState,
    })
    const { WSBase } = require('../../core/ws-base')
    const inst = WSBase.mock.instances[0]

    // 先 trigger close 启 polling.
    inst._handlers['close']({ code: 1006 })
    expect(precheckWs._isPollingActiveForTests()).toBe(true)

    // 然后重连成功 (authenticated event 触发).
    inst._handlers['authenticated']()
    expect(precheckWs._isPollingActiveForTests()).toBe(false)
    // onConnectionState 上报 isPollingFallback=false reason=ws_authenticated.
    expect(onConnectionState).toHaveBeenLastCalledWith({
      isPollingFallback: false,
      reason: 'ws_authenticated',
    })
  })

  test('AC#1+AC#4: polling tick (30s) 触发 onShouldRefresh', () => {
    const onShouldRefresh = jest.fn().mockResolvedValue(undefined)
    precheckWs.connect({
      orderId: 'o1',
      onEvent: jest.fn(),
      onShouldRefresh: onShouldRefresh,
    })
    const { WSBase } = require('../../core/ws-base')
    const inst = WSBase.mock.instances[0]

    inst._handlers['close']({ code: 1006 })
    expect(precheckWs._isPollingActiveForTests()).toBe(true)

    // 推进 29s — 未 tick.
    jest.advanceTimersByTime(29000)
    expect(onShouldRefresh).not.toHaveBeenCalled()

    // 再 1s = 30s — 一次 tick.
    jest.advanceTimersByTime(1000)
    expect(onShouldRefresh).toHaveBeenCalledTimes(1)

    // 再 30s — 二次 tick.
    jest.advanceTimersByTime(30000)
    expect(onShouldRefresh).toHaveBeenCalledTimes(2)
  })

  test('AC#1: 重复 call _startPolling 不创建双 timer (互斥 guard)', () => {
    const onShouldRefresh = jest.fn().mockResolvedValue(undefined)
    precheckWs.connect({
      orderId: 'o1',
      onEvent: jest.fn(),
      onShouldRefresh: onShouldRefresh,
    })
    const { WSBase } = require('../../core/ws-base')
    const inst = WSBase.mock.instances[0]

    // 两次 close (临时失败) — 第二次 应该 short-circuit 不创建新 timer.
    inst._handlers['close']({ code: 1006 })
    inst._handlers['close']({ code: 1011 })

    jest.advanceTimersByTime(30000)
    // 只应一个 timer tick — 不是 2 (if 双 timer 会 2 次).
    expect(onShouldRefresh).toHaveBeenCalledTimes(1)
  })

  test('AC#5: disconnect 停 polling + 清回调', () => {
    const onConnectionState = jest.fn()
    const onShouldRefresh = jest.fn().mockResolvedValue(undefined)
    precheckWs.connect({
      orderId: 'o1',
      onEvent: jest.fn(),
      onShouldRefresh: onShouldRefresh,
      onConnectionState: onConnectionState,
    })
    const { WSBase } = require('../../core/ws-base')
    const inst = WSBase.mock.instances[0]

    inst._handlers['close']({ code: 1006 })
    expect(precheckWs._isPollingActiveForTests()).toBe(true)

    precheckWs.disconnect()

    expect(precheckWs._isPollingActiveForTests()).toBe(false)
    // disconnect 后推进 timer — 不应 trigger onShouldRefresh
    jest.advanceTimersByTime(60000)
    expect(onShouldRefresh).not.toHaveBeenCalled()
  })

  test('AC#4: polling refresh Promise reject 不 停 polling (logger.warn 但 timer 继续)', () => {
    const onShouldRefresh = jest.fn().mockRejectedValue(new Error('network fail'))
    precheckWs.connect({
      orderId: 'o1',
      onEvent: jest.fn(),
      onShouldRefresh: onShouldRefresh,
    })
    const { WSBase } = require('../../core/ws-base')
    const inst = WSBase.mock.instances[0]

    inst._handlers['close']({ code: 1006 })

    // 三个 tick — 三次 调 (不仅 1 次 reject 后 停).
    jest.advanceTimersByTime(30000)
    jest.advanceTimersByTime(30000)
    jest.advanceTimersByTime(30000)
    expect(onShouldRefresh).toHaveBeenCalledTimes(3)
    expect(precheckWs._isPollingActiveForTests()).toBe(true)
  })

  test('AC#5: onConnectionState callback throw 不 冲击 _setPollingActive', () => {
    const onConnectionState = jest.fn(function () {
      throw new Error('page setData failed')
    })
    precheckWs.connect({
      orderId: 'o1',
      onEvent: jest.fn(),
      onConnectionState: onConnectionState,
    })
    const { WSBase } = require('../../core/ws-base')
    const inst = WSBase.mock.instances[0]

    // 不报错 throw to caller.
    expect(() => inst._handlers['close']({ code: 1006 })).not.toThrow()
    // polling 还是启了 (状态 module-level 独立 于 callback throw).
    expect(precheckWs._isPollingActiveForTests()).toBe(true)
  })
})
