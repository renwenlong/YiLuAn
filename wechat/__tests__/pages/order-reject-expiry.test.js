const { ORDER_STATUS, SERVICE_TYPES } = require('../../utils/constants')
const { orderAction } = require('../../services/order')

beforeEach(() => {
  jest.clearAllMocks()
  __resetWxStorage()
  wx.setStorageSync('yiluan_access_token', 'test_token')
})

describe('ORDER_STATUS constants', () => {
  test('includes rejected_by_companion status', () => {
    expect(ORDER_STATUS.rejected_by_companion).toBeDefined()
    expect(ORDER_STATUS.rejected_by_companion.label).toBe('陪诊师拒单')
    expect(ORDER_STATUS.rejected_by_companion.color).toBe('#FF4D4F')
  })

  test('includes expired status', () => {
    expect(ORDER_STATUS.expired).toBeDefined()
    expect(ORDER_STATUS.expired.label).toBe('已过期')
    expect(ORDER_STATUS.expired.color).toBe('#999999')
  })
})

describe('order reject action', () => {
  test('orderAction calls reject endpoint', async () => {
    __mockWxRequest(200, { id: 'o1', status: 'rejected_by_companion' })

    const result = await orderAction('o1', 'reject')
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('orders/o1/reject')
    expect(callArgs.method).toBe('POST')
    expect(result.status).toBe('rejected_by_companion')
  })
})

describe('notification service unread count', () => {
  test('getUnreadCount calls correct endpoint', async () => {
    const { getUnreadCount } = require('../../services/notification')
    __mockWxRequest(200, { count: 5 })

    const result = await getUnreadCount()
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('notifications/unread-count')
    expect(callArgs.method).toBe('GET')
    expect(result.count).toBe(5)
  })
})

describe('SERVICE_TYPES structure', () => {
  test('all service types have label and price', () => {
    Object.keys(SERVICE_TYPES).forEach(key => {
      expect(SERVICE_TYPES[key].label).toBeDefined()
      expect(SERVICE_TYPES[key].price).toBeGreaterThan(0)
    })
  })
})
