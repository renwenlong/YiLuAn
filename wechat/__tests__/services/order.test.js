const { getOrders, createOrder, getOrderDetail, orderAction, payOrder, refundOrder } = require('../../services/order')

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

    const orderData = { service_type: 'full_accompany', hospital_id: 'h1' }
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

  // Test 20: getOrderDetail calls GET /orders/:id
  test('getOrderDetail fetches order by id', async () => {
    __mockWxRequest(200, {
      id: 'o1',
      order_number: 'YLA123',
      status: 'created',
      appointment_date: '2026-04-15',
      appointment_time: '09:00',
      price: 299
    })

    const result = await getOrderDetail('o1')
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('orders/o1')
    expect(callArgs.method).toBe('GET')
    expect(result.id).toBe('o1')
    expect(result.appointment_date).toBe('2026-04-15')
    expect(result.price).toBe(299)
  })

  // Test 21: payOrder calls POST /orders/:id/pay
  test('payOrder sends pay request', async () => {
    __mockWxRequest(200, {
      id: 'p1',
      order_id: 'o1',
      amount: 299,
      payment_type: 'pay',
      status: 'success'
    })

    const result = await payOrder('o1')
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('orders/o1/pay')
    expect(callArgs.method).toBe('POST')
    expect(result.payment_type).toBe('pay')
    expect(result.status).toBe('success')
  })

  // Test 22: refundOrder calls POST /orders/:id/refund
  test('refundOrder sends refund request', async () => {
    __mockWxRequest(200, {
      id: 'p2',
      order_id: 'o1',
      amount: 299,
      payment_type: 'refund',
      status: 'success'
    })

    const result = await refundOrder('o1')
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('orders/o1/refund')
    expect(callArgs.method).toBe('POST')
    expect(result.payment_type).toBe('refund')
    expect(result.status).toBe('success')
  })

  // Test 23: getOrders without status param
  test('getOrders without status fetches all orders', async () => {
    __mockWxRequest(200, { items: [], total: 0 })

    await getOrders({ page: 1 })
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).not.toContain('status=')
    expect(callArgs.url).toContain('page=1')
  })

  // Test 24: orderAction for different actions
  test('orderAction works for start action', async () => {
    __mockWxRequest(200, { id: 'o1', status: 'in_progress' })

    const result = await orderAction('o1', 'start')
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('orders/o1/start')
    expect(result.status).toBe('in_progress')
  })

  test('orderAction works for complete action', async () => {
    __mockWxRequest(200, { id: 'o1', status: 'completed' })

    const result = await orderAction('o1', 'complete')
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('orders/o1/complete')
    expect(result.status).toBe('completed')
  })

  test('orderAction works for cancel action', async () => {
    __mockWxRequest(200, { id: 'o1', status: 'cancelled_by_patient' })

    const result = await orderAction('o1', 'cancel')
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('orders/o1/cancel')
    expect(result.status).toBe('cancelled_by_patient')
  })
})
