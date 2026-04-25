// [F-02] Notification deep-link navigation tests for wechat mini-program.
jest.mock('../../services/notification', () => ({
  getNotifications: jest.fn(),
  getUnreadCount: jest.fn(),
  markRead: jest.fn(),
  markAllRead: jest.fn(),
}))

jest.mock('../../store/index', () => {
  let _state = { user: { role: 'patient' } }
  return {
    getState: jest.fn(() => ({ ..._state })),
    setState: jest.fn((partial) => { _state = { ..._state, ...partial } }),
    _setMockState: (s) => { _state = s },
  }
})

global.Page = global.Page || jest.fn()

const notificationService = require('../../services/notification')
const store = require('../../store/index')

function loadPageConfig() {
  let pageConfig
  const origPage = global.Page
  global.Page = (config) => { pageConfig = config }
  jest.isolateModules(() => {
    require('../../pages/notification/index')
  })
  global.Page = origPage
  return pageConfig
}

function createPage(initialData) {
  const cfg = loadPageConfig()
  const page = Object.assign({}, cfg, { data: Object.assign({}, cfg.data, initialData) })
  page.setData = function (obj) { Object.assign(this.data, obj) }
  return page
}

beforeEach(() => {
  jest.clearAllMocks()
  __resetWxStorage()
  wx.setStorageSync('yiluan_access_token', 'test_token')
  wx.navigateTo = jest.fn()
})

describe('pages/notification — F-02 deep-link by target_type', () => {
  test('order target → patient order detail (patient role)', async () => {
    store._setMockState({ user: { role: 'patient' } })
    notificationService.markRead.mockResolvedValue({
      success: true,
      notification: {
        id: 'n1', is_read: true,
        target_type: 'order', target_id: 'order-abc',
      },
    })

    const page = createPage({
      notifications: [{
        id: 'n1', title: '订单更新', body: 'b', is_read: false,
        type: 'order_status_changed', reference_id: 'order-abc',
        target_type: 'order', target_id: 'order-abc',
      }],
      unreadCount: 1,
    })

    await page.onNotificationTap({ currentTarget: { dataset: { id: 'n1', read: false } } })
    expect(notificationService.markRead).toHaveBeenCalledWith('n1')
    expect(wx.navigateTo).toHaveBeenCalledWith({
      url: '/pages/patient/order-detail/index?id=order-abc',
    })
    expect(page.data.notifications[0].is_read).toBe(true)
    expect(page.data.unreadCount).toBe(0)
  })

  test('order target → companion order detail (companion role)', async () => {
    store._setMockState({ user: { role: 'companion' } })
    notificationService.markRead.mockResolvedValue({
      success: true,
      notification: {
        id: 'n2', is_read: true,
        target_type: 'order', target_id: 'order-xyz',
      },
    })

    const page = createPage({
      notifications: [{
        id: 'n2', title: '新订单', body: 'b', is_read: false,
        target_type: 'order', target_id: 'order-xyz',
      }],
      unreadCount: 1,
    })

    await page.onNotificationTap({ currentTarget: { dataset: { id: 'n2', read: false } } })
    expect(wx.navigateTo).toHaveBeenCalledWith({
      url: '/pages/companion/order-detail/index?id=order-xyz',
    })
  })

  test('companion target → companion detail page', async () => {
    store._setMockState({ user: { role: 'companion' } })
    notificationService.markRead.mockResolvedValue({
      success: true,
      notification: {
        id: 'n3', is_read: true,
        target_type: 'companion', target_id: 'cp-001',
      },
    })

    const page = createPage({
      notifications: [{
        id: 'n3', title: '资料已通过', body: 'b', is_read: false,
        target_type: 'companion', target_id: 'cp-001',
      }],
      unreadCount: 1,
    })

    await page.onNotificationTap({ currentTarget: { dataset: { id: 'n3', read: false } } })
    expect(wx.navigateTo).toHaveBeenCalledWith({
      url: '/pages/companion-detail/index?id=cp-001',
    })
  })

  test('review target → review write page', async () => {
    store._setMockState({ user: { role: 'companion' } })
    notificationService.markRead.mockResolvedValue({
      success: true,
      notification: {
        id: 'n4', is_read: true,
        target_type: 'review', target_id: 'review-77',
      },
    })

    const page = createPage({
      notifications: [{
        id: 'n4', title: '收到评价', body: 'b', is_read: false,
        target_type: 'review', target_id: 'review-77',
      }],
      unreadCount: 1,
    })

    await page.onNotificationTap({ currentTarget: { dataset: { id: 'n4', read: false } } })
    expect(wx.navigateTo).toHaveBeenCalledWith({
      url: '/pages/review/write/index?id=review-77',
    })
  })

  test('payment target → pay-result page', async () => {
    store._setMockState({ user: { role: 'patient' } })
    // already-read notification: should not mark again, navigate directly
    const page = createPage({
      notifications: [{
        id: 'n5', title: '支付完成', body: 'b', is_read: true,
        target_type: 'payment', target_id: 'pay-9',
      }],
      unreadCount: 0,
    })

    page.onNotificationTap({ currentTarget: { dataset: { id: 'n5', read: true } } })
    expect(notificationService.markRead).not.toHaveBeenCalled()
    expect(wx.navigateTo).toHaveBeenCalledWith({
      url: '/pages/patient/pay-result/index?id=pay-9',
    })
  })

  test('system target without id does not navigate', () => {
    store._setMockState({ user: { role: 'patient' } })
    const page = createPage({
      notifications: [{
        id: 'n6', title: '系统', body: 'b', is_read: true,
        target_type: 'system', target_id: null,
      }],
      unreadCount: 0,
    })
    page.onNotificationTap({ currentTarget: { dataset: { id: 'n6', read: true } } })
    expect(wx.navigateTo).not.toHaveBeenCalled()
  })

  test('legacy notification (no target_type) falls back to type/reference_id', async () => {
    store._setMockState({ user: { role: 'patient' } })
    notificationService.markRead.mockResolvedValue({ success: true, notification: null })

    const page = createPage({
      notifications: [{
        id: 'n7', title: '老通知', body: 'b', is_read: false,
        type: 'new_message', reference_id: 'order-legacy',
      }],
      unreadCount: 1,
    })
    await page.onNotificationTap({ currentTarget: { dataset: { id: 'n7', read: false } } })
    expect(wx.navigateTo).toHaveBeenCalledWith({
      url: '/pages/chat/room/index?order_id=order-legacy',
    })
  })

  test('mark-read backend response with notification updates local cache', async () => {
    store._setMockState({ user: { role: 'patient' } })
    notificationService.markRead.mockResolvedValue({
      success: true,
      notification: {
        id: 'n8', is_read: true,
        title: '后端最新标题', body: '后端最新正文',
        target_type: 'order', target_id: 'order-merged',
      },
    })

    const page = createPage({
      notifications: [{
        id: 'n8', title: '旧标题', body: '旧正文', is_read: false,
        target_type: 'order', target_id: 'order-merged',
      }],
      unreadCount: 1,
    })
    await page.onNotificationTap({ currentTarget: { dataset: { id: 'n8', read: false } } })
    expect(page.data.notifications[0].title).toBe('后端最新标题')
    expect(page.data.notifications[0].is_read).toBe(true)
  })
})
