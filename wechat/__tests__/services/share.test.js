const {
  exchangeShareSession,
  getShareOrder,
  createShare,
  listShares,
  revokeShare,
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

// ============================================================================
// ANDROID-DEV-WX-SHARE-ENTRY — 发起端 (Owner 路径, 本人 access token)
// ============================================================================
describe('services/share — 发起端 createShare/listShares/revokeShare', () => {
  beforeEach(() => {
    // 发起端走本人 access token (services/api.js request)
    wx.setStorageSync('yiluan_access_token', 'owner_token')
  })

  describe('createShare', () => {
    test('POST /orders/{id}/shares with share_scope, returns CreateShareResponse', async () => {
      __mockWxRequest(200, {
        id: 'tok-row-1',
        share_token: 'abc123',
        share_url: 'https://m.yiluan.cn/s/abc123',
        share_scope: 'full',
        share_expires_at: '2026-07-20T00:00:00Z',
        share_active_count: 1,
      })
      const out = await createShare('ord-1', 'full')
      const callArgs = wx.request.mock.calls[0][0]
      expect(callArgs.url).toContain('orders/ord-1/shares')
      expect(callArgs.method).toBe('POST')
      expect(callArgs.data).toEqual({ share_scope: 'full' })
      // 发起端必须带本人 access token
      expect(callArgs.header.Authorization).toBe('Bearer owner_token')
      expect(out.share_token).toBe('abc123')
      expect(out.share_url).toBe('https://m.yiluan.cn/s/abc123')
      expect(out.share_active_count).toBe(1)
    })

    test('defaults scope to full', async () => {
      __mockWxRequest(200, { id: 't', share_token: 'x', share_url: 'u', share_scope: 'full' })
      await createShare('ord-2')
      const callArgs = wx.request.mock.calls[0][0]
      expect(callArgs.data).toEqual({ share_scope: 'full' })
    })

    test('supports progress_only scope', async () => {
      __mockWxRequest(200, { id: 't', share_token: 'x', share_url: 'u', share_scope: 'progress_only' })
      await createShare('ord-3', 'progress_only')
      const callArgs = wx.request.mock.calls[0][0]
      expect(callArgs.data).toEqual({ share_scope: 'progress_only' })
    })

    test('rejects without orderId', async () => {
      await expect(createShare()).rejects.toThrow('orderId required')
      expect(wx.request).not.toHaveBeenCalled()
    })
  })

  describe('listShares', () => {
    test('GET /orders/{id}/shares returns ListSharesResponse', async () => {
      __mockWxRequest(200, {
        items: [
          { id: 't1', share_token: 'a', share_url: 'ua', share_scope: 'full', share_expires_at: '2026-07-20T00:00:00Z' },
          { id: 't2', share_token: 'b', share_url: 'ub', share_scope: 'progress_only', share_expires_at: '2026-07-21T00:00:00Z' },
        ],
        share_active_count: 2,
      })
      const out = await listShares('ord-1')
      const callArgs = wx.request.mock.calls[0][0]
      expect(callArgs.url).toContain('orders/ord-1/shares')
      expect(callArgs.method).toBe('GET')
      expect(callArgs.header.Authorization).toBe('Bearer owner_token')
      expect(out.items).toHaveLength(2)
      expect(out.share_active_count).toBe(2)
    })

    test('rejects without orderId', async () => {
      await expect(listShares()).rejects.toThrow('orderId required')
      expect(wx.request).not.toHaveBeenCalled()
    })
  })

  describe('revokeShare', () => {
    test('DELETE /orders/{id}/shares/{tokenId}', async () => {
      __mockWxRequest(200, {})
      await revokeShare('ord-1', 'tok-row-1')
      const callArgs = wx.request.mock.calls[0][0]
      expect(callArgs.url).toContain('orders/ord-1/shares/tok-row-1')
      expect(callArgs.method).toBe('DELETE')
      expect(callArgs.header.Authorization).toBe('Bearer owner_token')
    })

    test('rejects without orderId or tokenId', async () => {
      await expect(revokeShare('ord-1')).rejects.toThrow('orderId and tokenId required')
      await expect(revokeShare(undefined, 'tok')).rejects.toThrow('orderId and tokenId required')
      expect(wx.request).not.toHaveBeenCalled()
    })
  })

  test('发起端与接收端存储隔离: createShare 不碰 share_session', async () => {
    __mockWxRequest(200, { id: 't', share_token: 'x', share_url: 'u', share_scope: 'full' })
    await createShare('ord-1', 'full')
    // 发起端用本人 token, 不应写 share_session
    expect(wx.getStorageSync('yiluan_share_session')).toBe('')
  })
})
