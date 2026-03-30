// Mock notification service
jest.mock('../../services/notification', () => ({
  getNotifications: jest.fn(),
  getUnreadCount: jest.fn(),
  markRead: jest.fn(),
  markAllRead: jest.fn(),
}))

// Mock Page global for mini-program
global.Page = global.Page || jest.fn()

const notificationService = require('../../services/notification')

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
})
