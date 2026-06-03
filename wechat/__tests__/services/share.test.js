const {
  exchangeShareSession,
  getShareOrder,
} = require('../../services/share')
const {
  getShareSession,
  setShareSession,
  isShareSessionExpired,
  SHARE_SESSION_KEY,
  SHARE_SESSION_EXP_KEY,
} = require('../../utils/shareSession')

beforeEach(() => {
  jest.clearAllMocks()
  __resetWxStorage()
})

// Helper: drive wx.login success with a code
function mockWxLogin(code) {
  wx.login.mockImplementation((opts) => opts.success({ code }))
}

describe('utils/shareSession', () => {
  test('set/get/clear share_session roundtrip', () => {
    expect(getShareSession()).toBeNull()
    setShareSession('jwt_abc', '2026-06-03T00:30:00Z')
    expect(getShareSession()).toBe('jwt_abc')
    expect(wx.getStorageSync(SHARE_SESSION_EXP_KEY)).toBe(
      Date.parse('2026-06-03T00:30:00Z')
    )
  })

  test('isShareSessionExpired true when missing token', () => {
    expect(isShareSessionExpired()).toBe(true)
  })

  test('isShareSessionExpired true when exp passed, false when future', () => {
    setShareSession('jwt', Date.now() - 1000)
    expect(isShareSessionExpired()).toBe(true)
    setShareSession('jwt2', Date.now() + 60_000)
    expect(isShareSessionExpired()).toBe(false)
  })

  test('share_session storage key is isolated from access token key', () => {
    setShareSession('share_jwt', Date.now() + 60_000)
    // must not touch yiluan_access_token
    expect(wx.getStorageSync('yiluan_access_token')).toBe('')
    expect(wx.getStorageSync(SHARE_SESSION_KEY)).toBe('share_jwt')
  })
})

describe('services/share — exchangeShareSession', () => {
  test('wx.login → POST /shares/{token}/session, stores share_session', async () => {
    mockWxLogin('wx_code_xyz')
    wx.request.mockImplementation((opts) => {
      expect(opts.url).toContain('/shares/tok-1/session')
      expect(opts.method).toBe('POST')
      expect(opts.data).toEqual({ wx_openid: 'wx_code_xyz' })
      // share endpoint must NOT carry本人 access token
      expect(opts.header.Authorization).toBeUndefined()
      opts.success({
        statusCode: 200,
        data: {
          share_session: 'share_jwt_1',
          share_session_expires_at: '2026-06-03T00:30:00Z',
          share_scope: 'progress_only',
          order_id: 'ord-1',
        },
      })
    })

    const out = await exchangeShareSession('tok-1')
    expect(out).toEqual({
      share_scope: 'progress_only',
      order_id: 'ord-1',
      share_session_expires_at: '2026-06-03T00:30:00Z',
    })
    expect(getShareSession()).toBe('share_jwt_1')
    // JWT 串不外泄
    expect(out.share_session).toBeUndefined()
  })

  test('rejects without shareToken', async () => {
    await expect(exchangeShareSession()).rejects.toThrow('shareToken required')
    expect(wx.login).not.toHaveBeenCalled()
  })

  test('propagates wx.login failure', async () => {
    wx.login.mockImplementation((opts) => opts.fail(new Error('login boom')))
    await expect(exchangeShareSession('tok-1')).rejects.toThrow('login boom')
  })

  test('401 from /session (revoked token) rejects with statusCode', async () => {
    mockWxLogin('c')
    wx.request.mockImplementation((opts) =>
      opts.success({ statusCode: 401, data: { detail: 'revoked' } })
    )
    await expect(exchangeShareSession('tok-1')).rejects.toMatchObject({
      statusCode: 401,
    })
  })
})

describe('services/share — getShareOrder', () => {
  test('exchanges first (expired), then GET with share_session bearer', async () => {
    mockWxLogin('c1')
    const calls = []
    wx.request.mockImplementation((opts) => {
      calls.push(opts)
      if (opts.url.includes('/session') && opts.method === 'POST') {
        opts.success({
          statusCode: 200,
          data: {
            share_session: 'sjwt',
            share_session_expires_at: '2026-06-03T00:30:00Z',
            share_scope: 'full',
            order_id: 'o1',
          },
        })
      } else {
        // masked order view
        expect(opts.url).toContain('/shares/session/order')
        expect(opts.header.Authorization).toBe('Bearer sjwt')
        opts.success({
          statusCode: 200,
          data: {
            order_id: 'o1',
            patient_name_masked: '张**',
            share_scope: 'full',
            can_view_images: true,
          },
        })
      }
    })

    const view = await getShareOrder('tok-1')
    expect(view.patient_name_masked).toBe('张**')
    expect(calls).toHaveLength(2) // exchange + get
  })

  test('skips exchange when share_session still valid', async () => {
    setShareSession('valid_jwt', Date.now() + 120_000)
    wx.request.mockImplementation((opts) => {
      expect(opts.url).toContain('/shares/session/order')
      expect(opts.header.Authorization).toBe('Bearer valid_jwt')
      opts.success({
        statusCode: 200,
        data: { order_id: 'o9', patient_name_masked: '李**', share_scope: 'progress_only' },
      })
    })
    const view = await getShareOrder('tok-9')
    expect(wx.login).not.toHaveBeenCalled()
    expect(view.patient_name_masked).toBe('李**')
  })

  test('401 on order view triggers re-exchange then retry', async () => {
    setShareSession('stale_jwt', Date.now() + 120_000) // looks valid locally
    mockWxLogin('c2')
    let getAttempts = 0
    wx.request.mockImplementation((opts) => {
      if (opts.url.includes('/session') && opts.method === 'POST') {
        opts.success({
          statusCode: 200,
          data: {
            share_session: 'fresh_jwt',
            share_session_expires_at: '2026-06-03T00:30:00Z',
            share_scope: 'full',
            order_id: 'o1',
          },
        })
      } else {
        getAttempts += 1
        if (getAttempts === 1) {
          opts.success({ statusCode: 401, data: { detail: 'expired' } })
        } else {
          expect(opts.header.Authorization).toBe('Bearer fresh_jwt')
          opts.success({
            statusCode: 200,
            data: { order_id: 'o1', patient_name_masked: '王**', share_scope: 'full' },
          })
        }
      }
    })

    const view = await getShareOrder('tok-1')
    expect(view.patient_name_masked).toBe('王**')
    expect(getAttempts).toBe(2)
  })
})
