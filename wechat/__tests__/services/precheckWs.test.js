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
