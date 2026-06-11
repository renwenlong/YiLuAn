/**
 * Unit tests for services/precheck (S3-DEV-003-TRUST-UI-WX).
 */
const { getOrderPrecheckStatus } = require('../../services/precheck')

beforeEach(() => {
  jest.clearAllMocks()
  __resetWxStorage()
  wx.setStorageSync('yiluan_access_token', 'test_token')
})

describe('services/precheck', () => {
  test('getOrderPrecheckStatus calls GET users/orders/{id}/precheck-status', async () => {
    __mockWxRequest(200, {
      order_id: 'o1',
      contract_status: { ready: true },
      insurance_status: { ready: true },
      preparation_status: { ready: true },
      companion_cert_status: {
        ready: true,
        companion_cert_pseudonym_name: '陈师傅',
        companion_cert_work_id: 'PC0042',
        companion_cert_qualifications: ['康复治疗师'],
        companion_cert_verified_at: '2026-05-10T12:00:00Z',
      },
      all_ready: true,
      payment_enabled: true,
      blocked_reason: null,
    })
    const result = await getOrderPrecheckStatus('order-uuid-1')
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('users/orders/order-uuid-1/precheck-status')
    expect(callArgs.method).toBe('GET')
    expect(callArgs.header['Authorization']).toBe('Bearer test_token')
    expect(result.companion_cert_status.companion_cert_work_id).toBe('PC0042')
  })

  test('getOrderPrecheckStatus propagates 403/404 ABAC mask', async () => {
    __mockWxRequest(404, { detail: 'Not Found' })
    await expect(getOrderPrecheckStatus('other-order-id')).rejects.toBeDefined()
  })
})
