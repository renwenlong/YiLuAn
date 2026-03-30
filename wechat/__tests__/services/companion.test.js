const { getCompanions, getCompanionDetail, getCompanionReviews, applyCompanion, updateCompanionProfile } = require('../../services/companion')

beforeEach(() => {
  jest.clearAllMocks()
  __resetWxStorage()
  wx.setStorageSync('yiluan_access_token', 'test_token')
})

describe('services/companion', () => {
  // Test 1: getCompanions builds URL with params
  test('getCompanions builds URL with page and area params', async () => {
    __mockWxRequest(200, { list: [], total: 0 })

    await getCompanions({ page: 2, area: 'Beijing' })
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('companions')
    expect(callArgs.url).toContain('page=2')
    expect(callArgs.url).toContain('area=Beijing')
    expect(callArgs.method).toBe('GET')
  })

  // Test 2: getCompanionDetail fetches by ID
  test('getCompanionDetail fetches companion by ID', async () => {
    __mockWxRequest(200, { id: 'c1', name: 'Dr. Wang', avg_rating: 4.8 })

    const result = await getCompanionDetail('c1')
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('companions/c1')
    expect(callArgs.method).toBe('GET')
    expect(result.name).toBe('Dr. Wang')
  })

  // Test 3: applyCompanion sends POST with body
  test('applyCompanion sends POST to /companions/apply', async () => {
    __mockWxRequest(200, { id: 'c2', status: 'pending' })

    const data = { bio: 'Experienced nurse', service_area: 'Shanghai' }
    const result = await applyCompanion(data)
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('companions/apply')
    expect(callArgs.method).toBe('POST')
    expect(callArgs.data).toEqual(data)
    expect(result.status).toBe('pending')
  })

  // Test 4: updateCompanionProfile sends PUT
  test('updateCompanionProfile sends PUT to /companions/me', async () => {
    __mockWxRequest(200, { id: 'c1', bio: 'Updated bio', service_area: 'Guangzhou' })

    const data = { bio: 'Updated bio', service_area: 'Guangzhou' }
    const result = await updateCompanionProfile(data)
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('companions/me')
    expect(callArgs.method).toBe('PUT')
    expect(callArgs.data).toEqual(data)
    expect(result.bio).toBe('Updated bio')
  })

  // Test 5: getCompanionReviews fetches reviews by companion ID
  test('getCompanionReviews fetches reviews for companion', async () => {
    __mockWxRequest(200, { list: [{ id: 'r1', rating: 5, content: 'Great' }] })

    const result = await getCompanionReviews('c1')
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('companions/c1/reviews')
    expect(callArgs.method).toBe('GET')
    expect(result.list[0].rating).toBe(5)
  })

  // Test 6: getCompanionStats fetches companion stats
  test('getCompanionStats fetches companion stats', async () => {
    __mockWxRequest(200, { today_orders: 3, total_orders: 50, avg_rating: 4.8, total_earnings: 15000 })
    const { getCompanionStats } = require('../../services/companion')
    const result = await getCompanionStats()
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('companions/me/stats')
    expect(callArgs.method).toBe('GET')
  })
})
