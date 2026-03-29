const { wechatLogin, refreshToken, sendOTP, bindPhone, logout } = require('../../services/auth')

beforeEach(() => {
  jest.clearAllMocks()
  __resetWxStorage()
})

describe('services/auth', () => {
  // Test 7: wechatLogin calls wx.login then POST /wechat-login
  test('wechatLogin calls wx.login and posts code to backend', async () => {
    wx.login.mockImplementation((opts) => {
      opts.success({ code: 'wx_code_123' })
    })
    wx.request.mockImplementation((opts) => {
      opts.success({
        statusCode: 200,
        data: {
          access_token: 'at_1',
          refresh_token: 'rt_1',
          user: { id: 'u1', phone: null, role: null },
        },
      })
    })

    const user = await wechatLogin()
    expect(wx.login).toHaveBeenCalledTimes(1)
    expect(user).toEqual({ id: 'u1', phone: null, role: null })
  })

  // Test 8: wechatLogin stores tokens
  test('wechatLogin stores access and refresh tokens', async () => {
    wx.login.mockImplementation((opts) => {
      opts.success({ code: 'wx_code' })
    })
    wx.request.mockImplementation((opts) => {
      opts.success({
        statusCode: 200,
        data: {
          access_token: 'stored_at',
          refresh_token: 'stored_rt',
          user: { id: 'u1', phone: null, role: null },
        },
      })
    })

    await wechatLogin()
    expect(wx.getStorageSync('yiluan_access_token')).toBe('stored_at')
    expect(wx.getStorageSync('yiluan_refresh_token')).toBe('stored_rt')
  })

  // Test 9: wechatLogin returns user object
  test('wechatLogin resolves with user data', async () => {
    wx.login.mockImplementation((opts) => {
      opts.success({ code: 'c' })
    })
    wx.request.mockImplementation((opts) => {
      opts.success({
        statusCode: 200,
        data: {
          access_token: 'a',
          refresh_token: 'r',
          user: { id: 'uid', phone: '138', role: 'patient' },
        },
      })
    })

    const user = await wechatLogin()
    expect(user.id).toBe('uid')
    expect(user.role).toBe('patient')
  })

  // Test 10: refreshToken calls /auth/refresh
  test('refreshToken calls POST /auth/refresh', async () => {
    wx.setStorageSync('yiluan_refresh_token', 'old_rt')
    wx.request.mockImplementation((opts) => {
      opts.success({
        statusCode: 200,
        data: { access_token: 'new_at', refresh_token: 'new_rt' },
      })
    })

    const result = await refreshToken()
    expect(result.access_token).toBe('new_at')
    expect(wx.getStorageSync('yiluan_access_token')).toBe('new_at')
    expect(wx.getStorageSync('yiluan_refresh_token')).toBe('new_rt')
  })

  // Test 11: logout clears tokens and redirects
  test('logout clears tokens and redirects to login', () => {
    wx.setStorageSync('yiluan_access_token', 'at')
    wx.setStorageSync('yiluan_refresh_token', 'rt')

    logout()

    expect(wx.getStorageSync('yiluan_access_token')).toBeFalsy()
    expect(wx.getStorageSync('yiluan_refresh_token')).toBeFalsy()
    expect(wx.reLaunch).toHaveBeenCalledWith({ url: '/pages/login/index' })
  })

  // Test 12: sendOTP calls POST /auth/send-otp
  test('sendOTP sends phone to backend', async () => {
    wx.setStorageSync('yiluan_access_token', 'tok')
    wx.request.mockImplementation((opts) => {
      opts.success({ statusCode: 200, data: { message: 'OTP sent' } })
    })

    const result = await sendOTP('13800138000')
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.data).toEqual({ phone: '13800138000' })
    expect(result.message).toBe('OTP sent')
  })

  // Test 13: bindPhone calls POST /auth/bind-phone
  test('bindPhone sends phone+code to backend', async () => {
    wx.setStorageSync('yiluan_access_token', 'tok')
    wx.request.mockImplementation((opts) => {
      opts.success({
        statusCode: 200,
        data: { id: 'u1', phone: '13800138000', role: null },
      })
    })

    const result = await bindPhone('13800138000', '123456')
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.data).toEqual({ phone: '13800138000', code: '123456' })
    expect(result.phone).toBe('13800138000')
  })
})
