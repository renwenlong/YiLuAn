const {
  listEmergencyContacts,
  createEmergencyContact,
  updateEmergencyContact,
  deleteEmergencyContact,
  getEmergencyHotline,
  triggerEmergencyEvent,
} = require('../../services/emergency')

beforeEach(() => {
  jest.clearAllMocks()
  __resetWxStorage()
  wx.setStorageSync('yiluan_access_token', 'test_token')
})

describe('services/emergency', () => {
  test('listEmergencyContacts GET /emergency/contacts', async () => {
    __mockWxRequest(200, [{ id: 'c1', name: 'A', phone: '13900139000' }])
    const result = await listEmergencyContacts()
    const args = wx.request.mock.calls[0][0]
    expect(args.url).toContain('emergency/contacts')
    expect(args.method).toBe('GET')
    expect(result).toHaveLength(1)
  })

  test('createEmergencyContact POST /emergency/contacts', async () => {
    __mockWxRequest(201, { id: 'c1', name: 'A', phone: '13900139000', relationship: '朋友' })
    const data = { name: 'A', phone: '13900139000', relationship: '朋友' }
    const result = await createEmergencyContact(data)
    const args = wx.request.mock.calls[0][0]
    expect(args.url).toContain('emergency/contacts')
    expect(args.method).toBe('POST')
    expect(args.data).toEqual(data)
    expect(result.id).toBe('c1')
  })

  test('updateEmergencyContact PUT /emergency/contacts/:id', async () => {
    __mockWxRequest(200, { id: 'c1', name: 'B' })
    const result = await updateEmergencyContact('c1', { name: 'B' })
    const args = wx.request.mock.calls[0][0]
    expect(args.url).toContain('emergency/contacts/c1')
    expect(args.method).toBe('PUT')
    expect(result.name).toBe('B')
  })

  test('deleteEmergencyContact DELETE /emergency/contacts/:id', async () => {
    __mockWxRequest(204, '')
    await deleteEmergencyContact('c1')
    const args = wx.request.mock.calls[0][0]
    expect(args.url).toContain('emergency/contacts/c1')
    expect(args.method).toBe('DELETE')
  })

  test('getEmergencyHotline returns hotline', async () => {
    __mockWxRequest(200, { hotline: '4001234567' })
    const result = await getEmergencyHotline()
    expect(result.hotline).toBe('4001234567')
  })

  test('triggerEmergencyEvent POST /emergency/events with contact_id', async () => {
    __mockWxRequest(201, {
      event: { id: 'e1', contact_type: 'contact' },
      phone_to_call: '13900139000',
    })
    const result = await triggerEmergencyEvent({ contact_id: 'c1', order_id: 'o1' })
    const args = wx.request.mock.calls[0][0]
    expect(args.url).toContain('emergency/events')
    expect(args.method).toBe('POST')
    expect(args.data).toEqual({ contact_id: 'c1', order_id: 'o1' })
    expect(result.phone_to_call).toBe('13900139000')
  })

  test('triggerEmergencyEvent with hotline=true', async () => {
    __mockWxRequest(201, {
      event: { id: 'e1', contact_type: 'hotline' },
      phone_to_call: '4001234567',
    })
    const result = await triggerEmergencyEvent({ hotline: true })
    expect(result.event.contact_type).toBe('hotline')
    expect(result.phone_to_call).toBe('4001234567')
  })
})
