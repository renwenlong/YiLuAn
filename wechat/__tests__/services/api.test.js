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

  // Trace + timeout (PR: wx.request defaults)
  test('injects X-Request-Id header on every request', async () => {
    wx.setStorageSync('yiluan_access_token', 'tok')
    __mockWxRequest(200, { ok: true })
    await request({ url: 'orders' })
    const callArgs = wx.request.mock.calls[0][0]
    expect(typeof callArgs.header['X-Request-Id']).toBe('string')
    expect(callArgs.header['X-Request-Id'].length).toBeGreaterThan(4)
  })

  test('X-Request-Id is unique per call', async () => {
    wx.setStorageSync('yiluan_access_token', 'tok')
    __mockWxRequest(200, { ok: true })
    await request({ url: 'a' })
    await request({ url: 'b' })
    const id1 = wx.request.mock.calls[0][0].header['X-Request-Id']
    const id2 = wx.request.mock.calls[1][0].header['X-Request-Id']
    expect(id1).not.toBe(id2)
  })

  test('default request timeout is 15s, override is honoured', async () => {
    wx.setStorageSync('yiluan_access_token', 'tok')
    __mockWxRequest(200, { ok: true })
    await request({ url: 'a' })
    expect(wx.request.mock.calls[0][0].timeout).toBe(15000)

    await request({ url: 'b', timeout: 3000 })
    expect(wx.request.mock.calls[1][0].timeout).toBe(3000)
  })

  test('transport failure surfaces requestId for log correlation', async () => {
    wx.setStorageSync('yiluan_access_token', 'tok')
    wx.request.mockImplementation((options) => {
      options.fail({ errMsg: 'request:fail timeout' })
    })
    await expect(request({ url: 'slow' })).rejects.toMatchObject({
      statusCode: 0,
      requestId: expect.any(String),
    })
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

  // Test 12: concurrent 401s share a single refresh; all callers resolve
  // (Regression for the old _refreshQueue race.)
  test('concurrent 401s coalesce into one refresh and all retry', async () => {
    wx.setStorageSync('yiluan_access_token', 'old')
    wx.setStorageSync('yiluan_refresh_token', 'good_refresh')

    let refreshCalls = 0
    let businessCalls = 0
    wx.request.mockImplementation((options) => {
      if (options.url.endsWith('/auth/refresh')) {
        refreshCalls++
        // Resolve refresh asynchronously so both 401s land in the queue.
        setTimeout(() => {
          options.success({
            statusCode: 200,
            data: { access_token: 'new', refresh_token: 'new_r' },
          })
        }, 0)
        return
      }
      businessCalls++
      // First call from each request returns 401; retry returns 200.
      const isRetry = options.header && options.header.Authorization === 'Bearer new'
      if (isRetry) {
        options.success({ statusCode: 200, data: { ok: true, n: businessCalls } })
      } else {
        options.success({ statusCode: 401, data: {} })
      }
    })

    const [a, b] = await Promise.all([
      request({ url: 'a', method: 'GET' }),
      request({ url: 'b', method: 'GET' }),
    ])
    expect(a.ok).toBe(true)
    expect(b.ok).toBe(true)
    // Exactly ONE refresh fired despite two parallel 401s.
    expect(refreshCalls).toBe(1)
  })

  // Test 13: refresh network failure rejects every concurrent waiter
  // (no permanent-pending / infinite-spinner regression).
  test('refresh network failure rejects all queued requests', async () => {
    wx.setStorageSync('yiluan_access_token', 'old')
    wx.setStorageSync('yiluan_refresh_token', 'r')

    wx.request.mockImplementation((options) => {
      if (options.url.endsWith('/auth/refresh')) {
        setTimeout(() => options.fail({ errMsg: 'request:fail' }), 0)
        return
      }
      options.success({ statusCode: 401, data: {} })
    })

    const results = await Promise.allSettled([
      request({ url: 'a', method: 'GET' }),
      request({ url: 'b', method: 'GET' }),
      request({ url: 'c', method: 'GET' }),
    ])
    // All three must settle as rejections — not hang forever.
    expect(results.every((r) => r.status === 'rejected')).toBe(true)
    for (const r of results) {
      expect(r.reason.statusCode).toBe(0)
    }
  })
})
