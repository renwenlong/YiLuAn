const { getOrders, createOrder, orderAction } = require('../../services/order')

beforeEach(() => {
  jest.clearAllMocks()
  __resetWxStorage()
  wx.setStorageSync('yiluan_access_token', 'test_token')
})

describe('services/order', () => {
  // Test 17: getOrders calls GET /orders with query params
  test('getOrders fetches orders with pagination', async () => {
    __mockWxRequest(200, { items: [{ id: 'o1' }], total: 1 })

    const result = await getOrders({ status: 'created', page: 2 })
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('orders')
    expect(callArgs.url).toContain('status=created')
    expect(callArgs.url).toContain('page=2')
    expect(callArgs.method).toBe('GET')
    expect(result.items).toHaveLength(1)
  })

  // Test 18: createOrder calls POST /orders
  test('createOrder sends order data', async () => {
    __mockWxRequest(200, { id: 'o_new', status: 'created' })

    const orderData = { service_type: 'full_accompany', hospital_name: 'XX医院' }
    const result = await createOrder(orderData)
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.method).toBe('POST')
    expect(callArgs.data).toEqual(orderData)
    expect(result.id).toBe('o_new')
  })

  // Test 19: orderAction calls POST /orders/:id/:action
  test('orderAction sends action request', async () => {
    __mockWxRequest(200, { id: 'o1', status: 'accepted' })

    const result = await orderAction('o1', 'accept')
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('orders/o1/accept')
    expect(callArgs.method).toBe('POST')
    expect(result.status).toBe('accepted')
  })
})
