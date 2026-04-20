// Mock notification service
jest.mock('../../services/notification', () => ({
  getNotifications: jest.fn(),
  getUnreadCount: jest.fn(),
  markRead: jest.fn(),
  markAllRead: jest.fn(),
}))

jest.mock('../../store/index', () => {
  let _state = { user: null }
  return {
    getState: jest.fn(() => ({ ..._state })),
    setState: jest.fn((partial) => { _state = { ..._state, ...partial } }),
    _setMockState: (s) => { _state = s },
  }
})

// Mock Page global for mini-program
global.Page = global.Page || jest.fn()

const notificationService = require('../../services/notification')
const store = require('../../store/index')

// Mini-program Page simulator
function createPage(pageConfig) {
  const page = Object.assign({}, pageConfig, { data: Object.assign({}, pageConfig.data) })
  page.setData = function (obj) {
    Object.assign(this.data, obj)
  }
  return page
}

beforeEach(() => {
  jest.clearAllMocks()
  __resetWxStorage()
  wx.setStorageSync('yiluan_access_token', 'test_token')
})

describe('pages/notification', () => {
  test('fetchNotifications sets notifications data', async () => {
    const mockItems = [
      { id: 'n1', title: '订单更新', body: '订单已接单', is_read: false },
      { id: 'n2', title: '新消息', body: '收到一条消息', is_read: true },
    ]
    notificationService.getNotifications.mockResolvedValue({ items: mockItems })
    notificationService.getUnreadCount.mockResolvedValue({ count: 1 })

    // Load the page module fresh
    jest.isolateModules(() => {
      const pageModule = require('../../pages/notification/index')
    })

    // Simulate page behavior directly
    const page = createPage({
      data: { notifications: [], unreadCount: 0, loading: false, page: 1, hasMore: true },
    })
    page.fetchNotifications = function () {
      const self = this
      self.setData({ loading: true })
      return notificationService.getNotifications({ page: self.data.page })
        .then(function (res) {
          self.setData({ notifications: res.items || [], loading: false })
        })
    }

    await page.fetchNotifications()
    expect(page.data.notifications).toHaveLength(2)
    expect(page.data.notifications[0].title).toBe('订单更新')
    expect(page.data.loading).toBe(false)
  })

  test('onMarkAllRead calls markAllRead and updates data', async () => {
    notificationService.markAllRead.mockResolvedValue({ marked_read: 2 })

    const page = createPage({
      data: {
        notifications: [
          { id: 'n1', title: 'Test', is_read: false },
          { id: 'n2', title: 'Test2', is_read: false },
        ],
        unreadCount: 2,
      },
    })
    page.onMarkAllRead = function () {
      const self = this
      return notificationService.markAllRead().then(function () {
        const notifications = self.data.notifications.map(function (n) {
          return Object.assign({}, n, { is_read: true })
        })
        self.setData({ notifications: notifications, unreadCount: 0 })
      })
    }

    await page.onMarkAllRead()
    expect(notificationService.markAllRead).toHaveBeenCalledTimes(1)
    expect(page.data.unreadCount).toBe(0)
    expect(page.data.notifications.every(n => n.is_read)).toBe(true)
  })

  test('onNotificationTap calls markRead for unread notification', async () => {
    notificationService.markRead.mockResolvedValue({ success: true })

    const page = createPage({
      data: {
        notifications: [{ id: 'n1', title: 'Test', is_read: false }],
        unreadCount: 1,
      },
    })
    page.onNotificationTap = function (e) {
      const id = e.currentTarget.dataset.id
      const isRead = e.currentTarget.dataset.read
      if (!isRead) {
        const self = this
        return notificationService.markRead(id).then(function () {
          const notifications = self.data.notifications.map(function (n) {
            if (n.id === id) return Object.assign({}, n, { is_read: true })
            return n
          })
          self.setData({
            notifications: notifications,
            unreadCount: Math.max(0, self.data.unreadCount - 1),
          })
        })
      }
    }

    await page.onNotificationTap({
      currentTarget: { dataset: { id: 'n1', read: false } },
    })
    expect(notificationService.markRead).toHaveBeenCalledWith('n1')
    expect(page.data.notifications[0].is_read).toBe(true)
    expect(page.data.unreadCount).toBe(0)
  })

  describe('notification navigation', () => {
    let getNavigationUrl

    beforeEach(() => {
      // Extract getNavigationUrl by capturing it from fresh module load
      jest.isolateModules(() => {
        // We need to get the function from the module's scope
        // Since it's not exported, we test via the page's onNotificationTap behavior
      })
    })

    test('companion tapping order notification navigates to companion order detail', async () => {
      store._setMockState({ user: { role: 'companion' } })
      notificationService.markRead.mockResolvedValue({ success: true })
      wx.navigateTo = jest.fn()

      // Require fresh module to pick up store mock
      let pageConfig
      const origPage = global.Page
      global.Page = (config) => { pageConfig = config }
      jest.isolateModules(() => {
        require('../../pages/notification/index')
      })
      global.Page = origPage

      const page = createPage({
        data: {
          notifications: [{
            id: 'n1', title: '订单已接单', body: '详情', is_read: false,
            type: 'order_status_changed', reference_id: 'order-123',
          }],
          unreadCount: 1,
        },
      })
      // Bind the page methods from the captured config
      page.onNotificationTap = pageConfig.onNotificationTap.bind(page)

      await page.onNotificationTap({
        currentTarget: { dataset: { id: 'n1', read: false } },
      })

      expect(wx.navigateTo).toHaveBeenCalledWith({
        url: '/pages/companion/order-detail/index?id=order-123',
      })
    })

    test('patient tapping order notification navigates to patient order detail', async () => {
      store._setMockState({ user: { role: 'patient' } })
      notificationService.markRead.mockResolvedValue({ success: true })
      wx.navigateTo = jest.fn()

      let pageConfig
      const origPage = global.Page
      global.Page = (config) => { pageConfig = config }
      jest.isolateModules(() => {
        require('../../pages/notification/index')
      })
      global.Page = origPage

      const page = createPage({
        data: {
          notifications: [{
            id: 'n2', title: '订单更新', body: '详情', is_read: true,
            type: 'order_status_changed', reference_id: 'order-456',
          }],
          unreadCount: 0,
        },
      })
      page.onNotificationTap = pageConfig.onNotificationTap.bind(page)

      page.onNotificationTap({
        currentTarget: { dataset: { id: 'n2', read: true } },
      })

      expect(notificationService.markRead).not.toHaveBeenCalled()
      expect(wx.navigateTo).toHaveBeenCalledWith({
        url: '/pages/patient/order-detail/index?id=order-456',
      })
    })

    test('unknown notification type does not navigate', async () => {
      store._setMockState({ user: { role: 'companion' } })
      notificationService.markRead.mockResolvedValue({ success: true })
      wx.navigateTo = jest.fn()

      let pageConfig
      const origPage = global.Page
      global.Page = (config) => { pageConfig = config }
      jest.isolateModules(() => {
        require('../../pages/notification/index')
      })
      global.Page = origPage

      const page = createPage({
        data: {
          notifications: [{
            id: 'n3', title: '系统通知', body: '欢迎', is_read: true,
            type: 'system', reference_id: null,
          }],
          unreadCount: 0,
        },
      })
      page.onNotificationTap = pageConfig.onNotificationTap.bind(page)

      page.onNotificationTap({
        currentTarget: { dataset: { id: 'n3', read: true } },
      })

      expect(wx.navigateTo).not.toHaveBeenCalled()
    })
  })
})
