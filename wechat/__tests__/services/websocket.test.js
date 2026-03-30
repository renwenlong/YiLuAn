const ws = require('../../services/websocket')

let mockSocketTask

beforeEach(() => {
  jest.clearAllMocks()
  __resetWxStorage()
  wx.setStorageSync('yiluan_access_token', 'test_token')

  // Create a mock socket task
  mockSocketTask = {
    onOpen: jest.fn(),
    onMessage: jest.fn(),
    onClose: jest.fn(),
    onError: jest.fn(),
    send: jest.fn(),
    close: jest.fn(),
  }
  wx.connectSocket = jest.fn(() => mockSocketTask)
})

describe('services/websocket', () => {
  test('connect creates WebSocket with correct URL', () => {
    ws.connect({ orderId: 'order123' })

    expect(wx.connectSocket).toHaveBeenCalledTimes(1)
    const callArgs = wx.connectSocket.mock.calls[0][0]
    expect(callArgs.url).toContain('ws/chat/order123')
    expect(callArgs.url).toContain('token=test_token')
  })

  test('send serializes message as JSON', () => {
    ws.connect({ orderId: 'order123' })

    ws.send({ content: '你好', type: 'text' })
    expect(mockSocketTask.send).toHaveBeenCalledWith({
      data: JSON.stringify({ content: '你好', type: 'text' }),
    })
  })

  test('onMessage sets callback for incoming messages', () => {
    const callback = jest.fn()
    ws.onMessage(callback)
    ws.connect({ orderId: 'order123' })

    // Simulate receiving a message
    const onMessageFn = mockSocketTask.onMessage.mock.calls[0][0]
    onMessageFn({ data: JSON.stringify({ content: '收到', type: 'text' }) })

    expect(callback).toHaveBeenCalledWith({ content: '收到', type: 'text' })
  })

  test('disconnect closes socket and stops reconnect', () => {
    ws.connect({ orderId: 'order123' })
    ws.disconnect()

    expect(mockSocketTask.close).toHaveBeenCalled()
  })
})
