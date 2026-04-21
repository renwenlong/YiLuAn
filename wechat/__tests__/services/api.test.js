const { request } = require('../../services/api')

beforeEach(() => {
  jest.clearAllMocks()
  __resetWxStorage()
})

describe('services/api', () => {
  // Test 1: GET request with auth header
  test('sends GET request with Authorization header', async () => {
    wx.setStorageSync('yiluan_access_token', 'test_token_123')
    __mockWxRequest(200, { id: 1 })

    const result = await request({ url: 'users/me', method: 'GET' })

    expect(wx.request).toHaveBeenCalledTimes(1)
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.header['Authorization']).toBe('Bearer test_token_123')
    expect(callArgs.method).toBe('GET')
    expect(result).toEqual({ id: 1 })
  })

  // Test 2: POST request with body
  test('sends POST request with JSON body', async () => {
    wx.setStorageSync('yiluan_access_token', 'tok')
    __mockWxRequest(200, { ok: true })

    await request({ url: 'orders', method: 'POST', data: { type: 'full' } })

    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.method).toBe('POST')
    expect(callArgs.data).toEqual({ type: 'full' })
    expect(callArgs.header['Content-Type']).toBe('application/json')
  })

  // Test 3: 401 triggers refresh then retry
  test('retries with new token after 401 + successful refresh', async () => {
    wx.setStorageSync('yiluan_access_token', 'old_token')
    wx.setStorageSync('yiluan_refresh_token', 'refresh_tok')

    let callCount = 0
    wx.request.mockImplementation((options) => {
      callCount++
      if (callCount === 1) {
        // First call returns 401
        options.success({ statusCode: 401, data: { detail: 'Unauthorized' } })
      } else if (callCount === 2) {
        // Refresh call succeeds
        options.success({
          statusCode: 200,
          data: { access_token: 'new_token', refresh_token: 'new_refresh' },
        })
      } else {
        // Retry succeeds
        options.success({ statusCode: 200, data: { retried: true } })
      }
    })

    const result = await request({ url: 'users/me', method: 'GET' })
    expect(result).toEqual({ retried: true })
    expect(callCount).toBe(3)
  })

  // Test 4: Refresh failure forces logout
  test('forces logout when refresh token fails', async () => {
    wx.setStorageSync('yiluan_access_token', 'old')
    wx.setStorageSync('yiluan_refresh_token', 'bad_refresh')

    let callCount = 0
    wx.request.mockImplementation((options) => {
      callCount++
      if (callCount === 1) {
        options.success({ statusCode: 401, data: {} })
      } else {
        // Refresh fails
        options.success({ statusCode: 401, data: { detail: 'Invalid refresh' } })
      }
    })

    await expect(request({ url: 'test', method: 'GET' })).rejects.toMatchObject({
      statusCode: 401,
    })
    expect(wx.reLaunch).toHaveBeenCalledWith({ url: '/pages/login/index' })
  })

  // Test 5: Non-401 errors pass through
  test('rejects non-401 errors without refresh attempt', async () => {
    wx.setStorageSync('yiluan_access_token', 'tok')
    __mockWxRequest(500, { detail: 'Server error' })

    await expect(request({ url: 'test', method: 'GET' })).rejects.toMatchObject({
      statusCode: 500,
    })
    expect(wx.request).toHaveBeenCalledTimes(1)
  })

  // Test 6: auth=false skips Authorization header
  test('skips auth header when auth=false', async () => {
    wx.setStorageSync('yiluan_access_token', 'should_not_appear')
    __mockWxRequest(200, { ok: true })

    await request({ url: 'auth/wechat-login', method: 'POST', data: { code: 'x' }, auth: false })

    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.header['Authorization']).toBeUndefined()
  })

  // Test 7: PHONE_REQUIRED triggers modal + rejects as handled
  test('400 + PHONE_REQUIRED shows modal and rejects handled=true', async () => {
    wx.setStorageSync('yiluan_access_token', 'tok')
    __mockWxRequest(400, { detail: { error_code: 'PHONE_REQUIRED', message: '先绑手机号' } })

    await expect(request({ url: 'orders', method: 'POST' })).rejects.toMatchObject({
      statusCode: 400,
      handled: true,
    })
    expect(wx.showModal).toHaveBeenCalled()
    const modalArgs = wx.showModal.mock.calls[0][0]
    expect(modalArgs.title).toBe('请先绑定手机号')
  })

  // Test 8: PAYMENT_REQUIRED triggers modal + rejects as handled
  test('400 + PAYMENT_REQUIRED shows modal and rejects handled=true', async () => {
    wx.setStorageSync('yiluan_access_token', 'tok')
    __mockWxRequest(400, {
      detail: { error_code: 'PAYMENT_REQUIRED', message: '订单未支付' },
    })

    await expect(request({ url: 'orders/x/start', method: 'POST' })).rejects.toMatchObject({
      statusCode: 400,
      handled: true,
    })
    expect(wx.showModal).toHaveBeenCalled()
    expect(wx.showModal.mock.calls[0][0].title).toBe('订单尚未支付')
  })

  // Test 9: VERIFICATION_REQUIRED triggers modal + rejects as handled
  test('400 + VERIFICATION_REQUIRED shows modal and rejects handled=true', async () => {
    wx.setStorageSync('yiluan_access_token', 'tok')
    __mockWxRequest(400, {
      detail: { error_code: 'VERIFICATION_REQUIRED', message: '审核中' },
    })

    await expect(request({ url: 'orders/x/accept', method: 'POST' })).rejects.toMatchObject({
      statusCode: 400,
      handled: true,
    })
    expect(wx.showModal).toHaveBeenCalled()
    expect(wx.showModal.mock.calls[0][0].title).toBe('资质审核中')
  })

  // Test 10: _skipGuardHandlers bypasses modal and propagates raw rejection
  test('_skipGuardHandlers=true bypasses guard modals', async () => {
    wx.setStorageSync('yiluan_access_token', 'tok')
    __mockWxRequest(400, {
      detail: { error_code: 'PAYMENT_REQUIRED', message: 'pay first' },
    })

    const err = await request({
      url: 'orders/x/start',
      method: 'POST',
      _skipGuardHandlers: true,
    }).catch((e) => e)

    expect(err.statusCode).toBe(400)
    expect(err.handled).toBeUndefined()
    expect(wx.showModal).not.toHaveBeenCalled()
  })

  // Test 11: 400 without error_code still rejects without modal (legacy behavior)
  test('400 without error_code rejects without modal', async () => {
    wx.setStorageSync('yiluan_access_token', 'tok')
    __mockWxRequest(400, { detail: 'bad request' })

    await expect(request({ url: 'x', method: 'POST' })).rejects.toMatchObject({
      statusCode: 400,
    })
    expect(wx.showModal).not.toHaveBeenCalled()
  })
})
