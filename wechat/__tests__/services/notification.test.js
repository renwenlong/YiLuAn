const { getNotifications, getUnreadCount, markRead, markAllRead } = require('../../services/notification')

beforeEach(() => {
  jest.clearAllMocks()
  __resetWxStorage()
  wx.setStorageSync('yiluan_access_token', 'test_token')
})

describe('services/notification', () => {
  test('getNotifications fetches with default pagination', async () => {
    __mockWxRequest(200, { items: [{ id: 'n1', title: '通知1' }], total: 1 })

    const result = await getNotifications()
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('notifications')
    expect(callArgs.url).toContain('page=1')
    expect(callArgs.url).toContain('page_size=20')
    expect(callArgs.method).toBe('GET')
    expect(result.items).toHaveLength(1)
  })

  test('getNotifications with custom page', async () => {
    __mockWxRequest(200, { items: [], total: 5 })

    await getNotifications({ page: 3 })
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('page=3')
  })

  test('getUnreadCount fetches unread count', async () => {
    __mockWxRequest(200, { count: 5 })

    const result = await getUnreadCount()
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('notifications/unread-count')
    expect(callArgs.method).toBe('GET')
    expect(result.count).toBe(5)
  })

  test('markRead marks single notification as read', async () => {
    __mockWxRequest(200, { success: true })

    const result = await markRead('n1')
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('notifications/n1/read')
    expect(callArgs.method).toBe('POST')
    expect(result.success).toBe(true)
  })

  test('markAllRead marks all notifications as read', async () => {
    __mockWxRequest(200, { marked_read: 3 })

    const result = await markAllRead()
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('notifications/read-all')
    expect(callArgs.method).toBe('POST')
    expect(result.marked_read).toBe(3)
  })
})
