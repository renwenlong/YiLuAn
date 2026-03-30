const { submitReview, getReviews, getOrderReview } = require('../../services/review')

beforeEach(() => {
  jest.clearAllMocks()
  __resetWxStorage()
  wx.setStorageSync('yiluan_access_token', 'test_token')
})

describe('services/review', () => {
  test('submitReview sends POST with rating and content', async () => {
    __mockWxRequest(200, { id: 'r1', rating: 5, content: '非常满意' })

    const result = await submitReview({ orderId: 'o1', rating: 5, content: '非常满意' })
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('orders/o1/review')
    expect(callArgs.method).toBe('POST')
    expect(callArgs.data.rating).toBe(5)
    expect(callArgs.data.content).toBe('非常满意')
    expect(result.rating).toBe(5)
  })

  test('getReviews fetches companion reviews with pagination', async () => {
    __mockWxRequest(200, { items: [{ id: 'r1' }], total: 1 })

    const result = await getReviews('comp1', { page: 2 })
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('companions/comp1/reviews')
    expect(callArgs.url).toContain('page=2')
    expect(callArgs.method).toBe('GET')
    expect(result.items).toHaveLength(1)
  })

  test('getReviews defaults to page 1', async () => {
    __mockWxRequest(200, { items: [], total: 0 })

    await getReviews('comp1')
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('page=1')
  })

  test('getOrderReview fetches review for specific order', async () => {
    __mockWxRequest(200, { id: 'r1', order_id: 'o1', rating: 5 })

    const result = await getOrderReview('o1')
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('orders/o1/review')
    expect(callArgs.method).toBe('GET')
    expect(result.rating).toBe(5)
  })
})
