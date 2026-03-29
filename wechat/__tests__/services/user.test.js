const { getMe, updateMe } = require('../../services/user')

beforeEach(() => {
  jest.clearAllMocks()
  __resetWxStorage()
  wx.setStorageSync('yiluan_access_token', 'test_token')
})

describe('services/user', () => {
  // Test 14: getMe calls GET /users/me
  test('getMe fetches current user', async () => {
    __mockWxRequest(200, { id: 'u1', phone: '138', role: 'patient' })

    const user = await getMe()
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('users/me')
    expect(callArgs.method).toBe('GET')
    expect(user.id).toBe('u1')
  })

  // Test 15: updateMe calls PUT /users/me
  test('updateMe sends user data', async () => {
    __mockWxRequest(200, { id: 'u1', role: 'patient' })

    const result = await updateMe({ nickname: 'Test' })
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.method).toBe('PUT')
    expect(callArgs.data).toEqual({ nickname: 'Test' })
    expect(result.id).toBe('u1')
  })

  // Test 16: updateMe with role
  test('updateMe can set role', async () => {
    __mockWxRequest(200, { id: 'u1', role: 'companion' })

    const result = await updateMe({ role: 'companion' })
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.data).toEqual({ role: 'companion' })
    expect(result.role).toBe('companion')
  })
})
