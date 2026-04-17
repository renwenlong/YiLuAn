/**
 * Tests for services/notificationWs — 全局通知 WebSocket 封装
 * 覆盖：connect 成功 / 无 token 不连接 / 心跳 / 断线重连 / disconnect 停止重连
 */

const notificationWs = require('../../services/notificationWs')

// 由于模块内部有 module-level state，每个 test 之间需要 reset mock
beforeEach(() => {
  jest.useFakeTimers()
  jest.clearAllMocks()
  __resetWxStorage()
  // 彻底断开，清理上次测试残留
  notificationWs.disconnect()
})

afterEach(() => {
  jest.useRealTimers()
})

function _buildSocketTask() {
  const handlers = {}
  const task = {
    onOpen: jest.fn((cb) => { handlers.open = cb }),
    onMessage: jest.fn((cb) => { handlers.message = cb }),
    onClose: jest.fn((cb) => { handlers.close = cb }),
    onError: jest.fn((cb) => { handlers.error = cb }),
    send: jest.fn(),
    close: jest.fn(),
  }
  task._handlers = handlers
  return task
}

describe('services/notificationWs', () => {
  test('connect 无 access_token 时不会发起 wx.connectSocket', () => {
    notificationWs.connect({ onNotification: jest.fn() })
    expect(wx.connectSocket).not.toHaveBeenCalled()
  })

  test('connect 有 token 时发起 WebSocket 连接并附带 token query', () => {
    wx.setStorageSync('yiluan_access_token', 'tok_abc')
    const task = _buildSocketTask()
    wx.connectSocket.mockImplementation(() => task)

    notificationWs.connect({ onNotification: jest.fn() })

    expect(wx.connectSocket).toHaveBeenCalledTimes(1)
    const callArgs = wx.connectSocket.mock.calls[0][0]
    expect(callArgs.url).toMatch(/\/api\/v1\/ws\/notifications\?token=tok_abc/)
  })

  test('onOpen 后每 30s 发送 ping 心跳', () => {
    wx.setStorageSync('yiluan_access_token', 'tok')
    const task = _buildSocketTask()
    wx.connectSocket.mockImplementation(() => task)

    notificationWs.connect({ onNotification: jest.fn() })
    task._handlers.open()

    // 心跳 30s 触发一次
    jest.advanceTimersByTime(30000)
    expect(task.send).toHaveBeenCalledTimes(1)
    const sent = JSON.parse(task.send.mock.calls[0][0].data)
    expect(sent.type).toBe('ping')

    jest.advanceTimersByTime(30000)
    expect(task.send).toHaveBeenCalledTimes(2)
  })

  test('onMessage 过滤 pong，其他通知交给回调', () => {
    wx.setStorageSync('yiluan_access_token', 'tok')
    const task = _buildSocketTask()
    wx.connectSocket.mockImplementation(() => task)
    const cb = jest.fn()

    notificationWs.connect({ onNotification: cb })
    task._handlers.message({ data: JSON.stringify({ type: 'pong' }) })
    expect(cb).not.toHaveBeenCalled()

    task._handlers.message({
      data: JSON.stringify({ type: 'new_order', order_id: 'o1' }),
    })
    expect(cb).toHaveBeenCalledWith({ type: 'new_order', order_id: 'o1' })
  })

  test('disconnect 调用 socketTask.close 且后续 onClose 不再重连', () => {
    wx.setStorageSync('yiluan_access_token', 'tok')
    const task = _buildSocketTask()
    wx.connectSocket.mockImplementation(() => task)

    notificationWs.connect({ onNotification: jest.fn() })
    notificationWs.disconnect()

    expect(task.close).toHaveBeenCalled()

    // 模拟关闭事件：计数器已被推到 MAX，不应再触发新 connect
    wx.connectSocket.mockClear()
    task._handlers.close && task._handlers.close()
    jest.advanceTimersByTime(60000)
    expect(wx.connectSocket).not.toHaveBeenCalled()
  })

  test('onClose 触发指数退避重连（第一次 1s）', () => {
    wx.setStorageSync('yiluan_access_token', 'tok')
    const task1 = _buildSocketTask()
    const task2 = _buildSocketTask()
    wx.connectSocket
      .mockImplementationOnce(() => task1)
      .mockImplementationOnce(() => task2)

    notificationWs.connect({ onNotification: jest.fn() })
    task1._handlers.open()
    // 对端关闭
    task1._handlers.close()

    // 1 秒后应重连
    jest.advanceTimersByTime(1000)
    expect(wx.connectSocket).toHaveBeenCalledTimes(2)
  })
})
