/**
 * Backward-compat smoke tests for the thin wrappers introduced in C-12.
 * These pin the public export shape of services/websocket.js and
 * services/notificationWs.js so existing call-sites don't break.
 */

describe('services/websocket — thin wrapper public API', () => {
  const ws = require('../../services/websocket')

  test('exports connect / send / onMessage / disconnect', () => {
    expect(typeof ws.connect).toBe('function')
    expect(typeof ws.send).toBe('function')
    expect(typeof ws.onMessage).toBe('function')
    expect(typeof ws.disconnect).toBe('function')
  })
})

describe('services/notificationWs — thin wrapper public API', () => {
  const notifWs = require('../../services/notificationWs')

  test('exports connect / disconnect', () => {
    expect(typeof notifWs.connect).toBe('function')
    expect(typeof notifWs.disconnect).toBe('function')
  })
})

describe('services/notificationWs — connect routes through WSBase', () => {
  const notifWs = require('../../services/notificationWs')

  beforeEach(() => {
    jest.clearAllMocks()
    __resetWxStorage()
    wx.setStorageSync('yiluan_access_token', 'tk-1')
    wx.connectSocket = jest.fn(() => ({
      onOpen: jest.fn(),
      onMessage: jest.fn(),
      onClose: jest.fn(),
      onError: jest.fn(),
      send: jest.fn(),
      close: jest.fn(),
    }))
  })

  test('connect builds the notifications URL with token', () => {
    notifWs.connect({ onNotification: () => {} })
    expect(wx.connectSocket).toHaveBeenCalledTimes(1)
    const url = wx.connectSocket.mock.calls[0][0].url
    expect(url).toContain('/api/v1/ws/notifications')
    expect(url).toContain('token=tk-1')
    notifWs.disconnect()
  })

  test('connect without token short-circuits (no socket created)', () => {
    __resetWxStorage()
    notifWs.connect({ onNotification: () => {} })
    expect(wx.connectSocket).not.toHaveBeenCalled()
  })
})
