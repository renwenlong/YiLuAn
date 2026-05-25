jest.mock('../../config/index', () => ({
  API_BASE_URL: 'https://example.test/api/v1',
}))
jest.mock('../../utils/token', () => ({
  getAccessToken: jest.fn(),
}))

const token = require('../../utils/token')
const telemetryReporter = require('../../utils/telemetryReporter')

describe('utils/telemetryReporter', () => {
  beforeEach(() => {
    wx.request.mockReset()
    token.getAccessToken.mockReset()
  })

  test('endpoint 指向 /telemetry/events', () => {
    expect(telemetryReporter._endpoint).toBe('/telemetry/events')
  })

  test('buildLoggerReporter 把 LogEvent 包成 telemetry 事件并 POST', () => {
    const reporter = telemetryReporter.buildLoggerReporter()
    reporter({
      level: 'error',
      message: 'boom',
      context: { code: 'NET', page: 'pages/x/y', env: 'prod', stack: 'trace' },
      ts: 1716624000000,
    })
    expect(wx.request).toHaveBeenCalledTimes(1)
    const call = wx.request.mock.calls[0][0]
    expect(call.method).toBe('POST')
    expect(call.url).toBe('https://example.test/api/v1/telemetry/events')
    expect(call.data.event_type).toBe('logger.error')
    expect(call.data.payload).toMatchObject({ code: 'NET', message: 'boom', stack: 'trace' })
    // page / env 应该被提到 client_meta，不在 payload 里
    expect(call.data.payload).not.toHaveProperty('page')
    expect(call.data.payload).not.toHaveProperty('env')
    expect(call.data.client_meta).toEqual({ page: 'pages/x/y', env: 'prod' })
    expect(call.data.ts).toBe(1716624000000)
  })

  test('buildLoggerReporter 在有 token 时带 Authorization header', () => {
    token.getAccessToken.mockReturnValue('abc.def.ghi')
    const reporter = telemetryReporter.buildLoggerReporter()
    reporter({ level: 'warn', message: 'x', context: {}, ts: 1 })
    const call = wx.request.mock.calls[0][0]
    expect(call.header.Authorization).toBe('Bearer abc.def.ghi')
  })

  test('buildLoggerReporter 没 token 时不带 Authorization（匿名上报）', () => {
    token.getAccessToken.mockReturnValue(null)
    const reporter = telemetryReporter.buildLoggerReporter()
    reporter({ level: 'warn', message: 'x', context: {}, ts: 1 })
    const call = wx.request.mock.calls[0][0]
    expect(call.header.Authorization).toBeUndefined()
  })

  test('buildLoggerReporter 在 token 抛错时仍能完成上报', () => {
    token.getAccessToken.mockImplementation(() => { throw new Error('storage down') })
    const reporter = telemetryReporter.buildLoggerReporter()
    expect(() => reporter({ level: 'warn', message: 'x', context: {}, ts: 1 })).not.toThrow()
    expect(wx.request).toHaveBeenCalled()
  })

  test('buildLoggerReporter 截断 message 到 1024 字符', () => {
    const reporter = telemetryReporter.buildLoggerReporter()
    const huge = 'x'.repeat(2048)
    reporter({ level: 'error', message: huge, context: {}, ts: 1 })
    const call = wx.request.mock.calls[0][0]
    expect(call.data.payload.message.length).toBe(1024)
  })

  test('buildAnalyticsEmitter 直接透传 telemetry 形状事件', () => {
    const emitter = telemetryReporter.buildAnalyticsEmitter()
    emitter({
      event_type: 'funnel.order_submit',
      payload: { order_id: 'o1' },
      client_meta: { env: 'prod', page: 'pages/x' },
      ts: 1234,
    })
    expect(wx.request).toHaveBeenCalledTimes(1)
    const call = wx.request.mock.calls[0][0]
    expect(call.data).toEqual({
      event_type: 'funnel.order_submit',
      payload: { order_id: 'o1' },
      client_meta: { env: 'prod', page: 'pages/x' },
      ts: 1234,
    })
  })

  test('buildAnalyticsEmitter 拒绝空事件 / 无 event_type', () => {
    const emitter = telemetryReporter.buildAnalyticsEmitter()
    emitter(null)
    emitter({})
    emitter({ payload: {} })
    expect(wx.request).not.toHaveBeenCalled()
  })

  test('wx.request 自身抛错时被吞掉（绝不二次抛）', () => {
    wx.request.mockImplementation(() => { throw new Error('network layer crash') })
    const reporter = telemetryReporter.buildLoggerReporter()
    expect(() => reporter({ level: 'warn', message: 'x', context: {}, ts: 1 })).not.toThrow()
  })

  test('logger 事件无 ts 时 fallback 到 Date.now()', () => {
    const before = Date.now()
    const reporter = telemetryReporter.buildLoggerReporter()
    reporter({ level: 'warn', message: 'x', context: {} })
    const after = Date.now()
    const call = wx.request.mock.calls[0][0]
    expect(call.data.ts).toBeGreaterThanOrEqual(before)
    expect(call.data.ts).toBeLessThanOrEqual(after)
  })
})
