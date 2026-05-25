// Tests for utils/degradation — local weak-network fallback flag.
const degradation = require('../../utils/degradation')

describe('utils/degradation', () => {
  beforeEach(() => {
    global.__resetWxStorage()
    degradation.clearDegraded()
  })

  test('starts not degraded', () => {
    expect(degradation.isDegraded()).toBe(false)
    expect(degradation.getDegradedReason()).toBe(null)
  })

  test('setDegraded / clearDegraded toggles flag', () => {
    degradation.setDegraded('manual_test')
    expect(degradation.isDegraded()).toBe(true)
    expect(degradation.getDegradedReason()).toBe('manual_test')
    degradation.clearDegraded()
    expect(degradation.isDegraded()).toBe(false)
  })

  test('trips after 3 timeout failures on same scope', () => {
    const err = { statusCode: 0, data: { errMsg: 'request:fail timeout' } }
    expect(degradation.recordFailure('order_submit', err)).toBe(false)
    expect(degradation.recordFailure('order_submit', err)).toBe(false)
    const tripped = degradation.recordFailure('order_submit', err)
    expect(tripped).toBe(true)
    expect(degradation.isDegraded()).toBe(true)
    expect(degradation.getDegradedReason()).toBe('order_submit_threshold')
  })

  test('trips on 5xx server errors', () => {
    const err = { statusCode: 503, data: {} }
    degradation.recordFailure('pay', err)
    degradation.recordFailure('pay', err)
    degradation.recordFailure('pay', err)
    expect(degradation.isDegraded()).toBe(true)
  })

  test('does NOT trip on 4xx client errors', () => {
    const err = { statusCode: 400, data: { detail: 'bad input' } }
    for (let i = 0; i < 5; i++) degradation.recordFailure('order_submit', err)
    expect(degradation.isDegraded()).toBe(false)
  })

  test('success clears counters and degraded flag', () => {
    const err = { statusCode: 0 }
    degradation.recordFailure('order_submit', err)
    degradation.recordFailure('order_submit', err)
    degradation.recordFailure('order_submit', err)
    expect(degradation.isDegraded()).toBe(true)
    degradation.recordSuccess('order_submit')
    expect(degradation.isDegraded()).toBe(false)
  })

  test('subscribe fires on state change', () => {
    const cb = jest.fn()
    const unsub = degradation.subscribe(cb)
    degradation.setDegraded('x')
    expect(cb).toHaveBeenCalledWith(true)
    degradation.clearDegraded()
    expect(cb).toHaveBeenCalledWith(false)
    unsub()
    cb.mockClear()
    degradation.setDegraded('y')
    expect(cb).not.toHaveBeenCalled()
  })

  test('track records success when promise resolves', async () => {
    await degradation.track('order_submit', () => Promise.resolve({ ok: 1 }))
    expect(degradation.isDegraded()).toBe(false)
  })

  test('track records failure and trips after threshold', async () => {
    const err = { statusCode: 500 }
    for (let i = 0; i < 3; i++) {
      try {
        await degradation.track('pay', () => Promise.reject(err))
      } catch (e) {
        // expected
      }
    }
    expect(degradation.isDegraded()).toBe(true)
  })

  test('TTL auto-expires degraded state', () => {
    degradation.setDegraded('test')
    expect(degradation.isDegraded()).toBe(true)
    // poke storage to backdate the timestamp past TTL
    const past = Date.now() - degradation._internal.DEGRADE_TTL_MS - 1000
    wx.setStorageSync(degradation._internal.STATE_KEY, {
      degraded: true,
      reason: 'test',
      ts: past,
    })
    expect(degradation.isDegraded()).toBe(false)
  })
})
