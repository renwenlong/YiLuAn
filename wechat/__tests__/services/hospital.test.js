const { getHospitals, getHospitalDetail } = require('../../services/hospital')

beforeEach(() => {
  jest.clearAllMocks()
  __resetWxStorage()
  wx.setStorageSync('yiluan_access_token', 'test_token')
})

describe('services/hospital', () => {
  // Test 1: getHospitals with keyword
  test('getHospitals builds URL with keyword param', async () => {
    __mockWxRequest(200, { list: [{ id: 'h1', name: 'Beijing Hospital' }] })

    await getHospitals({ keyword: '北京' })
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('hospitals')
    expect(callArgs.url).toContain('keyword=' + encodeURIComponent('北京'))
    expect(callArgs.method).toBe('GET')
  })

  // Test 2: getHospitals with no params
  test('getHospitals without params fetches all', async () => {
    __mockWxRequest(200, { list: [] })

    await getHospitals()
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toMatch(/hospitals$/)
    expect(callArgs.method).toBe('GET')
  })

  // Test 3: getHospitalDetail fetches by ID
  test('getHospitalDetail fetches hospital by ID', async () => {
    __mockWxRequest(200, { id: 'h1', name: 'Beijing Hospital', address: 'Haidian' })

    const result = await getHospitalDetail('h1')
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('hospitals/h1')
    expect(callArgs.method).toBe('GET')
    expect(result.name).toBe('Beijing Hospital')
    expect(result.address).toBe('Haidian')
  })
})
