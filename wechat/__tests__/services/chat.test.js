const { getChatMessages, sendMessage, markRead } = require('../../services/chat')

beforeEach(() => {
  jest.clearAllMocks()
  __resetWxStorage()
  wx.setStorageSync('yiluan_access_token', 'test_token')
})

describe('services/chat', () => {
  test('getChatMessages fetches messages for order', async () => {
    __mockWxRequest(200, { items: [{ id: 'm1', content: '你好' }], total: 1 })

    const result = await getChatMessages('o1')
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('chats/o1/messages')
    expect(callArgs.method).toBe('GET')
    expect(result.items).toHaveLength(1)
  })

  test('getChatMessages passes before cursor', async () => {
    __mockWxRequest(200, { items: [], total: 0 })

    await getChatMessages('o1', { before: 'cursor123' })
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('before=cursor123')
  })

  test('sendMessage posts message to order chat', async () => {
    __mockWxRequest(200, { id: 'm1', content: '你好', type: 'text' })

    const result = await sendMessage('o1', { content: '你好', type: 'text' })
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('chats/o1/messages')
    expect(callArgs.method).toBe('POST')
    expect(callArgs.data.content).toBe('你好')
    expect(result.type).toBe('text')
  })

  test('sendMessage sends image type', async () => {
    __mockWxRequest(200, { id: 'm2', content: 'https://example.com/img.jpg', type: 'image' })

    const result = await sendMessage('o1', { content: 'https://example.com/img.jpg', type: 'image' })
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.data.type).toBe('image')
    expect(result.type).toBe('image')
  })

  test('markRead posts read request for order', async () => {
    __mockWxRequest(200, { marked_read: 3 })

    const result = await markRead('o1')
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('chats/o1/read')
    expect(callArgs.method).toBe('POST')
    expect(result.marked_read).toBe(3)
  })
})
