/**
 * Tests for services/shareWs — 家属分享只读进度 WebSocket
 * 覆盖：
 *  - 缺 shareToken / 缺 share_session / share_session 过期 → 不连接
 *  - 有效 session → 发起连接，URL 含 /ws/share/{token}，token 不进 query
 *  - onOpen 首帧发 {type:"share_auth", session}，之后 30s ping
 *  - onMessage 吞 share_auth_ok，location_replay + 进度帧抛给回调
 *  - 断线指数退避重连
 *  - disconnect 停止重连
 */
const shareWs = require('../../services/shareWs')
const {
  setShareSession,
  clearShareSession,
  SHARE_SESSION_KEY,
  SHARE_SESSION_EXP_KEY,
} = require('../../utils/shareSession')

beforeEach(() => {
  jest.useFakeTimers()
  jest.clearAllMocks()
  __resetWxStorage()
  shareWs.disconnect()
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

// 存一枚 30min 后过期的有效 share_session
function _setValidSession(token) {
  wx.setStorageSync(SHARE_SESSION_KEY, token || 'sess_jwt')
  wx.setStorageSync(SHARE_SESSION_EXP_KEY, Date.now() + 30 * 60 * 1000)
}

describe('services/shareWs', () => {
  test('缺 shareToken 时不发起连接', () => {
    _setValidSession()
    shareWs.connect({ onProgress: jest.fn() })
    expect(wx.connectSocket).not.toHaveBeenCalled()
  })

  test('缺 share_session 时不发起连接', () => {
    clearShareSession()
    shareWs.connect({ shareToken: 'tk1', onProgress: jest.fn() })
    expect(wx.connectSocket).not.toHaveBeenCalled()
  })

  test('share_session 已过期时不发起连接', () => {
    wx.setStorageSync(SHARE_SESSION_KEY, 'sess_jwt')
    wx.setStorageSync(SHARE_SESSION_EXP_KEY, Date.now() - 1000) // 已过期
    shareWs.connect({ shareToken: 'tk1', onProgress: jest.fn() })
    expect(wx.connectSocket).not.toHaveBeenCalled()
  })

  test('有效 session 发起连接：URL 含 /ws/share/{token}，token 不进 query', () => {
    _setValidSession()
    const task = _buildSocketTask()
    wx.connectSocket.mockImplementation(() => task)

    shareWs.connect({ shareToken: 'tk_abc', onProgress: jest.fn() })

    expect(wx.connectSocket).toHaveBeenCalledTimes(1)
    const url = wx.connectSocket.mock.calls[0][0].url
    expect(url).toMatch(/\/api\/v1\/ws\/share\/tk_abc$/)
    expect(url).not.toContain('session=')
    expect(url).not.toContain('token=')
  })

  test('onOpen 首帧发 {type:"share_auth", session}，之后 30s ping', () => {
    _setValidSession('jwt_xyz')
    const task = _buildSocketTask()
    wx.connectSocket.mockImplementation(() => task)

    shareWs.connect({ shareToken: 'tk1', onProgress: jest.fn() })
    task._handlers.open()

    expect(task.send).toHaveBeenCalledTimes(1)
    const authFrame = JSON.parse(task.send.mock.calls[0][0].data)
    expect(authFrame.type).toBe('share_auth')
    expect(authFrame.session).toBe('jwt_xyz')

    jest.advanceTimersByTime(30000)
    expect(task.send).toHaveBeenCalledTimes(2)
    const pingFrame = JSON.parse(task.send.mock.calls[1][0].data)
    expect(pingFrame.type).toBe('ping')
  })

  test('onMessage 吞 share_auth_ok，location_replay 与进度帧抛给回调', () => {
    _setValidSession()
    const task = _buildSocketTask()
    wx.connectSocket.mockImplementation(() => task)
    const cb = jest.fn()

    shareWs.connect({ shareToken: 'tk1', onProgress: cb })

    // 握手 ack 吞掉
    task._handlers.message({ data: JSON.stringify({ type: 'share_auth_ok' }) })
    expect(cb).not.toHaveBeenCalled()

    // 重连补偿帧 → 抛
    task._handlers.message({
      data: JSON.stringify({ type: 'location_replay', data: { lat: 1, lng: 2 } }),
    })
    expect(cb).toHaveBeenCalledWith({ type: 'location_replay', data: { lat: 1, lng: 2 } })

    // 实时进度帧 → 抛
    task._handlers.message({
      data: JSON.stringify({ type: 'order_progress', status: 'in_service' }),
    })
    expect(cb).toHaveBeenCalledWith({ type: 'order_progress', status: 'in_service' })
    expect(cb).toHaveBeenCalledTimes(2)
  })

  test('onClose 触发指数退避重连（第一次 1s 后重连）', () => {
    _setValidSession()
    const task1 = _buildSocketTask()
    const task2 = _buildSocketTask()
    wx.connectSocket
      .mockImplementationOnce(() => task1)
      .mockImplementationOnce(() => task2)

    shareWs.connect({ shareToken: 'tk1', onProgress: jest.fn() })
    expect(wx.connectSocket).toHaveBeenCalledTimes(1)

    task1._handlers.close({ code: 1006 })
    jest.advanceTimersByTime(1000)
    expect(wx.connectSocket).toHaveBeenCalledTimes(2)
  })

  test('disconnect 调用 close 且后续不再重连', () => {
    _setValidSession()
    const task = _buildSocketTask()
    wx.connectSocket.mockImplementation(() => task)

    shareWs.connect({ shareToken: 'tk1', onProgress: jest.fn() })
    shareWs.disconnect()
    expect(task.close).toHaveBeenCalled()

    wx.connectSocket.mockClear()
    task._handlers.close && task._handlers.close({ code: 1000 })
    jest.advanceTimersByTime(60000)
    expect(wx.connectSocket).not.toHaveBeenCalled()
  })
})
