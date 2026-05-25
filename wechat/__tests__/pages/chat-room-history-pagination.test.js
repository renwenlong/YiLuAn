// Pull-up history pagination on the chat room page.
jest.mock('../../services/chat', () => ({
  getChatMessages: jest.fn(),
  markRead: jest.fn().mockResolvedValue({ marked_read: 0 }),
}))
jest.mock('../../services/order', () => ({
  getOrderDetail: jest.fn().mockResolvedValue({ status: 'accepted' }),
  orderAction: jest.fn(),
}))
jest.mock('../../pages/chat/room/services/websocket', () => ({
  connect: jest.fn(),
  send: jest.fn(),
  disconnect: jest.fn(),
}))
jest.mock('../../store/index', () => ({
  getState: () => ({ user: { id: 'u-self' } }),
}))

global.Page = global.Page || jest.fn()

const chatSvc = require('../../services/chat')

function loadPage() {
  let cfg
  const orig = global.Page
  global.Page = (c) => { cfg = c }
  jest.isolateModules(() => {
    require('../../pages/chat/room/index')
  })
  global.Page = orig
  return cfg
}

function createPage(initial = {}) {
  const cfg = loadPage()
  const page = Object.assign({}, cfg, {
    data: Object.assign({}, cfg.data, initial),
  })
  page.setData = function (obj) { Object.assign(this.data, obj) }
  return page
}

beforeEach(() => {
  jest.clearAllMocks()
  __resetWxStorage()
  wx.showToast = jest.fn()
})

describe('pages/chat/room — pull-up history pagination', () => {
  test('loadHistory seeds oldestId and hasMoreHistory from response', async () => {
    chatSvc.getChatMessages.mockResolvedValueOnce({
      items: [
        { id: 'm10', sender_id: 'u-other', content: 'old', created_at: 't1' },
        { id: 'm11', sender_id: 'u-self', content: 'mid', created_at: 't2' },
      ],
      total: 50,
      has_more: true,
    })
    const page = createPage({ orderId: 'o1' })

    await page.loadHistory()

    expect(chatSvc.getChatMessages).toHaveBeenCalledWith('o1', { limit: 30 })
    expect(page.data.oldestId).toBe('m10')
    expect(page.data.hasMoreHistory).toBe(true)
    expect(page.data.historyExhausted).toBe(false)
    expect(page.data.messages).toHaveLength(2)
  })

  test('onScrollToUpper prepends older page and updates cursor', async () => {
    const page = createPage({
      orderId: 'o1',
      messages: [
        { id: 'm10', sender_id: 'u-other', content: 'a' },
        { id: 'm11', sender_id: 'u-self', content: 'b' },
      ],
      oldestId: 'm10',
      hasMoreHistory: true,
      historyExhausted: false,
    })

    chatSvc.getChatMessages.mockResolvedValueOnce({
      items: [
        { id: 'm7', content: 'older-a' },
        { id: 'm8', content: 'older-b' },
        { id: 'm9', content: 'older-c' },
      ],
      total: 50,
      has_more: true,
    })

    await page.onScrollToUpper()

    expect(chatSvc.getChatMessages).toHaveBeenCalledWith('o1', {
      beforeId: 'm10',
      limit: 30,
    })
    expect(page.data.messages.map((m) => m.id)).toEqual([
      'm7', 'm8', 'm9', 'm10', 'm11',
    ])
    expect(page.data.oldestId).toBe('m7')
    expect(page.data.hasMoreHistory).toBe(true)
    expect(page.data.loadingMore).toBe(false)
    // Anchor scroll position on the formerly-first message so the viewport
    // doesn't snap to the top.
    expect(page.data.scrollIntoView).toBe('msg-3')
  })

  test('onScrollToUpper marks history exhausted when server says no more', async () => {
    const page = createPage({
      orderId: 'o1',
      messages: [{ id: 'm10', sender_id: 'u-other', content: 'a' }],
      oldestId: 'm10',
      hasMoreHistory: true,
      historyExhausted: false,
    })

    chatSvc.getChatMessages.mockResolvedValueOnce({
      items: [{ id: 'm1', content: 'first ever' }],
      total: 2,
      has_more: false,
    })

    await page.onScrollToUpper()

    expect(page.data.historyExhausted).toBe(true)
    expect(page.data.hasMoreHistory).toBe(false)
    expect(page.data.messages.map((m) => m.id)).toEqual(['m1', 'm10'])
  })

  test('onScrollToUpper is a no-op when already exhausted', async () => {
    const page = createPage({
      orderId: 'o1',
      messages: [{ id: 'm10' }],
      oldestId: 'm10',
      historyExhausted: true,
      hasMoreHistory: false,
    })

    await page.onScrollToUpper()

    expect(chatSvc.getChatMessages).not.toHaveBeenCalled()
  })

  test('onScrollToUpper is a no-op while loadingMore is true', async () => {
    const page = createPage({
      orderId: 'o1',
      messages: [{ id: 'm10' }],
      oldestId: 'm10',
      loadingMore: true,
    })

    await page.onScrollToUpper()

    expect(chatSvc.getChatMessages).not.toHaveBeenCalled()
  })

  test('onScrollToUpper recovers gracefully on request failure', async () => {
    const page = createPage({
      orderId: 'o1',
      messages: [{ id: 'm10' }],
      oldestId: 'm10',
      hasMoreHistory: true,
    })

    chatSvc.getChatMessages.mockRejectedValueOnce(new Error('boom'))

    await page.onScrollToUpper()

    expect(page.data.loadingMore).toBe(false)
    expect(wx.showToast).toHaveBeenCalledWith(
      expect.objectContaining({ icon: 'none' })
    )
  })
})
