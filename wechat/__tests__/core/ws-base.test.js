/**
 * Unit tests for wechat/core/ws-base.js — covers reconnect backoff,
 * heartbeat scheduling, nonce auto-injection + 5-min LRU dedup, and
 * the on/off event hooks.
 */
const { WSBase, _nanoid } = require('../../core/ws-base')

function makeMockSocket() {
  return {
    _open: null,
    _msg: null,
    _close: null,
    _err: null,
    onOpen(fn) { this._open = fn },
    onMessage(fn) { this._msg = fn },
    onClose(fn) { this._close = fn },
    onError(fn) { this._err = fn },
    send: jest.fn(),
    close: jest.fn(),
  }
}

describe('core/ws-base', () => {
  test('_nanoid produces a string of requested length', () => {
    const a = _nanoid(16)
    const b = _nanoid(16)
    expect(typeof a).toBe('string')
    expect(a.length).toBe(16)
    expect(a).not.toBe(b) // collision essentially impossible
  })

  test('connect → open hook fires + heartbeat starts', () => {
    const sock = makeMockSocket()
    const opens = []
    const setIntervalSpy = jest.fn(() => 999)
    const ws = new WSBase({
      socketFactory: () => sock,
      heartbeatMs: 30000,
      setInterval: setIntervalSpy,
      clearInterval: jest.fn(),
    })
    ws.on('open', () => opens.push(true))
    ws.connect('ws://x')
    sock._open()

    expect(opens).toEqual([true])
    expect(setIntervalSpy).toHaveBeenCalledTimes(1)
    expect(setIntervalSpy.mock.calls[0][1]).toBe(30000)
  })

  test('send auto-injects nonce and dedupes repeats within TTL', () => {
    const sock = makeMockSocket()
    const ws = new WSBase({ socketFactory: () => sock })
    ws.connect('ws://x')
    sock._open()

    const r1 = ws.send({ content: 'a', type: 'text' })
    expect(r1.sent).toBe(true)
    expect(r1.deduped).toBe(false)
    expect(typeof r1.nonce).toBe('string')

    // Re-send same nonce → short-circuit (no second send call)
    const r2 = ws.send({ content: 'a', type: 'text', nonce: r1.nonce })
    expect(r2.sent).toBe(false)
    expect(r2.deduped).toBe(true)
    expect(sock.send).toHaveBeenCalledTimes(1)
  })

  test('send withNonce:false skips nonce injection', () => {
    const sock = makeMockSocket()
    const ws = new WSBase({ socketFactory: () => sock })
    ws.connect('ws://x')
    sock._open()
    ws.send({ type: 'ping' }, { withNonce: false })
    const sent = JSON.parse(sock.send.mock.calls[0][0].data)
    expect(sent.nonce).toBeUndefined()
  })

  test('reconnect uses exponential backoff ladder 1/2/5/10/30', () => {
    const sock = makeMockSocket()
    const timeouts = []
    const setTimeoutSpy = jest.fn((fn, delay) => {
      timeouts.push(delay)
      return timeouts.length
    })
    const ws = new WSBase({
      socketFactory: () => sock,
      setTimeout: setTimeoutSpy,
      clearTimeout: jest.fn(),
      setInterval: jest.fn(() => 1),
      clearInterval: jest.fn(),
      maxReconnect: 5,
    })
    ws.connect('ws://x')

    // simulate 5 close events without ever firing the scheduled fn
    for (let i = 0; i < 5; i++) sock._close()

    expect(timeouts).toEqual([1000, 2000, 5000, 10000, 30000])
  })

  test('disconnect prevents further reconnect scheduling', () => {
    const sock = makeMockSocket()
    const setTimeoutSpy = jest.fn(() => 1)
    const clearTimeoutSpy = jest.fn()
    const ws = new WSBase({
      socketFactory: () => sock,
      setTimeout: setTimeoutSpy,
      clearTimeout: clearTimeoutSpy,
      setInterval: jest.fn(() => 1),
      clearInterval: jest.fn(),
    })
    ws.connect('ws://x')
    ws.disconnect()
    sock._close()
    expect(setTimeoutSpy).not.toHaveBeenCalled()
    expect(sock.close).toHaveBeenCalled()
  })

  test('pong frames are swallowed (not delivered to message handler)', () => {
    const sock = makeMockSocket()
    const msgs = []
    const ws = new WSBase({ socketFactory: () => sock })
    ws.on('message', (d) => msgs.push(d))
    ws.connect('ws://x')
    sock._open()
    sock._msg({ data: JSON.stringify({ type: 'pong' }) })
    sock._msg({ data: JSON.stringify({ type: 'text', content: 'hi' }) })
    expect(msgs).toEqual([{ type: 'text', content: 'hi' }])
  })

  test('invalid JSON message does not throw and is ignored', () => {
    const sock = makeMockSocket()
    const msgs = []
    const ws = new WSBase({ socketFactory: () => sock })
    ws.on('message', (d) => msgs.push(d))
    ws.connect('ws://x')
    sock._open()
    expect(() => sock._msg({ data: '{not json' })).not.toThrow()
    expect(msgs).toEqual([])
  })
})
