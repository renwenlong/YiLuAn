// [F-07] services/followupReminder smoke tests
const {
  createFollowupReminder,
  listMyFollowupReminders,
  cancelFollowupReminder,
} = require('../../services/followupReminder')

beforeEach(() => {
  jest.clearAllMocks()
  __resetWxStorage()
  wx.setStorageSync('yiluan_access_token', 'test_token')
})

describe('services/followupReminder', () => {
  test('createFollowupReminder POST /orders/{id}/followup-reminders', async () => {
    __mockWxRequest(201, {
      id: 'r1', user_id: 'u1', order_id: 'o1',
      remind_at: '2026-06-01T03:00:00Z', status: 'pending',
      attempts: 0, note: '取报告', sent_at: null,
      created_at: '2026-05-20T00:00:00Z',
    })
    const r = await createFollowupReminder('o1', {
      order_id: 'o1', remind_at: '2026-06-01T03:00:00Z', note: '取报告',
    })
    const args = wx.request.mock.calls[0][0]
    expect(args.url).toContain('orders/o1/followup-reminders')
    expect(args.method).toBe('POST')
    expect(args.data.order_id).toBe('o1')
    expect(r.status).toBe('pending')
  })

  test('listMyFollowupReminders GET /orders/me/followup-reminders', async () => {
    __mockWxRequest(200, { items: [], total: 0 })
    await listMyFollowupReminders()
    const args = wx.request.mock.calls[0][0]
    expect(args.url).toContain('orders/me/followup-reminders')
    expect(args.method).toBe('GET')
  })

  test('cancelFollowupReminder DELETE /orders/me/followup-reminders/{id}', async () => {
    __mockWxRequest(204, null)
    await cancelFollowupReminder('r1')
    const args = wx.request.mock.calls[0][0]
    expect(args.url).toContain('orders/me/followup-reminders/r1')
    expect(args.method).toBe('DELETE')
  })
})
