/**
 * Order Full Lifecycle Tests
 *
 * Validates the complete order flow from patient perspective:
 *   create → pay → accept → request-start → confirm-start → complete → review
 * And the cancel/refund flow.
 *
 * Also has per-stage tests for quick debugging when the full lifecycle test fails.
 */

const { createOrder, getOrderDetail, orderAction, payOrder, refundOrder } = require('../../services/order')
const { submitReview } = require('../../services/review')

// Track call index for sequential mock responses
let _callIndex = 0

beforeEach(() => {
  jest.clearAllMocks()
  __resetWxStorage()
  wx.setStorageSync('yiluan_access_token', 'test_token')
  _callIndex = 0
})

/**
 * Helper: mock wx.request to return different responses for sequential calls.
 * Each call to wx.request returns the next response in the array.
 */
function __mockWxRequestSequence(responses) {
  _callIndex = 0
  wx.request.mockImplementation((options) => {
    const resp = responses[_callIndex] || { statusCode: 200, data: {} }
    _callIndex++
    if (options.success) {
      options.success({ statusCode: resp.statusCode || 200, data: resp.data })
    }
  })
}

// ---------------------------------------------------------------------------
// Full Lifecycle Tests
// ---------------------------------------------------------------------------
describe('Order Full Lifecycle', () => {
  test('complete lifecycle: create → pay → accept → request-start → confirm-start → complete → review', async () => {
    __mockWxRequestSequence([
      // 1. createOrder
      { data: { id: 'order-1', status: 'created', price: 299, order_number: 'YLA001' } },
      // 2. payOrder
      { data: { id: 'pay-1', order_id: 'order-1', amount: 299, payment_type: 'pay', status: 'success' } },
      // 3. orderAction accept
      { data: { id: 'order-1', status: 'accepted', companion_id: 'comp-1' } },
      // 4. orderAction request-start
      { data: { id: 'order-1', status: 'accepted' } },
      // 5. orderAction confirm-start
      { data: { id: 'order-1', status: 'in_progress' } },
      // 6. orderAction complete
      { data: { id: 'order-1', status: 'completed' } },
      // 7. submitReview
      { data: { id: 'rev-1', order_id: 'order-1', rating: 5, content: '非常满意', companion_id: 'comp-1' } },
    ])

    // Step 1: Create order
    const order = await createOrder({
      service_type: 'full_accompany',
      hospital_id: 'h1',
      appointment_date: '2026-06-01',
      appointment_time: '09:00',
    })
    expect(order.status).toBe('created')
    expect(order.price).toBe(299)

    // Step 2: Pay
    const payment = await payOrder('order-1')
    expect(payment.payment_type).toBe('pay')
    expect(payment.amount).toBe(299)

    // Step 3: Accept
    const accepted = await orderAction('order-1', 'accept')
    expect(accepted.status).toBe('accepted')
    expect(accepted.companion_id).toBe('comp-1')

    // Step 4: Request start (no status change)
    const reqStart = await orderAction('order-1', 'request-start')
    expect(reqStart.status).toBe('accepted')

    // Step 5: Confirm start
    const confirmed = await orderAction('order-1', 'confirm-start')
    expect(confirmed.status).toBe('in_progress')

    // Step 6: Complete
    const completed = await orderAction('order-1', 'complete')
    expect(completed.status).toBe('completed')

    // Step 7: Review
    const review = await submitReview({
      orderId: 'order-1',
      rating: 5,
      content: '非常满意',
    })
    expect(review.rating).toBe(5)
    expect(review.companion_id).toBe('comp-1')

    // Verify all 7 calls were made
    expect(wx.request).toHaveBeenCalledTimes(7)

    // Verify URL/method of each call
    const calls = wx.request.mock.calls.map(c => c[0])
    expect(calls[0].method).toBe('POST')       // createOrder
    expect(calls[0].url).toContain('orders')
    expect(calls[1].url).toContain('orders/order-1/pay')
    expect(calls[2].url).toContain('orders/order-1/accept')
    expect(calls[3].url).toContain('orders/order-1/request-start')
    expect(calls[4].url).toContain('orders/order-1/confirm-start')
    expect(calls[5].url).toContain('orders/order-1/complete')
    expect(calls[6].url).toContain('orders/order-1/review')
  })

  test('cancel lifecycle with refund', async () => {
    __mockWxRequestSequence([
      // 1. createOrder
      { data: { id: 'order-2', status: 'created', price: 299 } },
      // 2. payOrder
      { data: { id: 'pay-2', amount: 299, payment_type: 'pay', status: 'success' } },
      // 3. cancel
      { data: { id: 'order-2', status: 'cancelled_by_patient' } },
      // 4. refundOrder
      { data: { id: 'ref-1', order_id: 'order-2', amount: 299, payment_type: 'refund', status: 'success' } },
    ])

    const order = await createOrder({
      service_type: 'full_accompany',
      hospital_id: 'h1',
      appointment_date: '2026-06-01',
      appointment_time: '10:00',
    })
    expect(order.status).toBe('created')

    await payOrder('order-2')

    const cancelled = await orderAction('order-2', 'cancel')
    expect(cancelled.status).toBe('cancelled_by_patient')

    const refund = await refundOrder('order-2')
    expect(refund.payment_type).toBe('refund')
    expect(refund.amount).toBe(299)

    expect(wx.request).toHaveBeenCalledTimes(4)
  })
})

// ---------------------------------------------------------------------------
// Stage Tests — quick debugging when full lifecycle fails
// ---------------------------------------------------------------------------
describe('Order Lifecycle Stage Tests', () => {
  test('Stage 1: createOrder sends correct payload', async () => {
    __mockWxRequest(200, { id: 'o1', status: 'created', price: 299, order_number: 'YLA001' })

    const data = {
      service_type: 'full_accompany',
      hospital_id: 'h1',
      appointment_date: '2026-06-01',
      appointment_time: '09:00',
      description: '需要全程陪诊',
    }
    const result = await createOrder(data)
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.method).toBe('POST')
    expect(callArgs.url).toContain('orders')
    expect(callArgs.data).toEqual(data)
    expect(result.status).toBe('created')
    expect(result.price).toBe(299)
  })

  test('Stage 2: payOrder calls POST /orders/:id/pay', async () => {
    __mockWxRequest(200, {
      id: 'p1', order_id: 'o1', amount: 299, payment_type: 'pay', status: 'success',
    })

    const result = await payOrder('o1')
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('orders/o1/pay')
    expect(callArgs.method).toBe('POST')
    expect(result.payment_type).toBe('pay')
    expect(result.amount).toBe(299)
    expect(result.status).toBe('success')
  })

  test('Stage 3: orderAction accept calls POST /orders/:id/accept', async () => {
    __mockWxRequest(200, { id: 'o1', status: 'accepted', companion_id: 'c1', companion_name: '张护士' })

    const result = await orderAction('o1', 'accept')
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('orders/o1/accept')
    expect(callArgs.method).toBe('POST')
    expect(result.status).toBe('accepted')
    expect(result.companion_id).toBe('c1')
  })

  test('Stage 4a: orderAction request-start calls correct URL', async () => {
    __mockWxRequest(200, { id: 'o1', status: 'accepted' })

    const result = await orderAction('o1', 'request-start')
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('orders/o1/request-start')
    expect(callArgs.method).toBe('POST')
    expect(result.status).toBe('accepted')
  })

  test('Stage 4b: orderAction confirm-start calls correct URL', async () => {
    __mockWxRequest(200, { id: 'o1', status: 'in_progress' })

    const result = await orderAction('o1', 'confirm-start')
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('orders/o1/confirm-start')
    expect(callArgs.method).toBe('POST')
    expect(result.status).toBe('in_progress')
  })

  test('Stage 5: orderAction complete calls correct URL', async () => {
    __mockWxRequest(200, { id: 'o1', status: 'completed' })

    const result = await orderAction('o1', 'complete')
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('orders/o1/complete')
    expect(callArgs.method).toBe('POST')
    expect(result.status).toBe('completed')
  })

  test('Stage 6: submitReview sends rating and content to correct URL', async () => {
    __mockWxRequest(200, { id: 'r1', order_id: 'o1', rating: 5, content: '很好', companion_id: 'c1' })

    const result = await submitReview({ orderId: 'o1', rating: 5, content: '很好' })
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('orders/o1/review')
    expect(callArgs.method).toBe('POST')
    expect(callArgs.data).toEqual({ rating: 5, content: '很好' })
    expect(result.rating).toBe(5)
  })

  test('Stage 7: orderAction cancel calls correct URL', async () => {
    __mockWxRequest(200, { id: 'o1', status: 'cancelled_by_patient' })

    const result = await orderAction('o1', 'cancel')
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('orders/o1/cancel')
    expect(callArgs.method).toBe('POST')
    expect(result.status).toBe('cancelled_by_patient')
  })

  test('Stage 8: refundOrder calls POST /orders/:id/refund', async () => {
    __mockWxRequest(200, { id: 'ref1', order_id: 'o1', amount: 299, payment_type: 'refund', status: 'success' })

    const result = await refundOrder('o1')
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('orders/o1/refund')
    expect(callArgs.method).toBe('POST')
    expect(result.payment_type).toBe('refund')
  })

  test('Stage 9: getOrderDetail returns order with payment_status', async () => {
    __mockWxRequest(200, {
      id: 'o1',
      status: 'created',
      price: 299,
      payment_status: 'paid',
      order_number: 'YLA123',
      timeline: [{ title: '订单已创建', time: '2026-06-01 09:00' }],
    })

    const result = await getOrderDetail('o1')
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('orders/o1')
    expect(callArgs.method).toBe('GET')
    expect(result.payment_status).toBe('paid')
    expect(result.timeline).toHaveLength(1)
  })
})
