const { payOrder, requestWechatPayment } = require('../../services/order')

beforeEach(() => {
  jest.clearAllMocks()
  __resetWxStorage()
  wx.setStorageSync('yiluan_access_token', 'test_token')
})

describe('requestWechatPayment', () => {
  // Test: mock provider skips wx.requestPayment
  test('mock provider resolves immediately without calling wx.requestPayment', async () => {
    const payResult = {
      payment_id: 'p1',
      provider: 'mock',
      prepay_id: 'mock_prepay_123',
      sign_params: {
        appId: 'wx_mock_appid',
        timeStamp: '1700000000',
        nonceStr: 'abc123',
        package: 'prepay_id=mock_prepay_123',
        signType: 'RSA',
        paySign: 'mock_sign_abc'
      },
      mock_success: true
    }

    const result = await requestWechatPayment(payResult)
    expect(result.success).toBe(true)
    expect(result.mock).toBe(true)
    expect(wx.requestPayment).not.toHaveBeenCalled()
  })

  // Test: mock_success flag also skips wx.requestPayment
  test('mock_success=true skips wx.requestPayment even if provider is wechat', async () => {
    const payResult = {
      payment_id: 'p2',
      provider: 'wechat',
      mock_success: true,
      sign_params: null
    }

    const result = await requestWechatPayment(payResult)
    expect(result.success).toBe(true)
    expect(result.mock).toBe(true)
    expect(wx.requestPayment).not.toHaveBeenCalled()
  })

  // Test: wechat provider calls wx.requestPayment with correct params
  test('wechat provider calls wx.requestPayment with mapped sign_params', async () => {
    const signParams = {
      appId: 'wx_real_appid',
      timeStamp: '1700000001',
      nonceStr: 'nonce_xyz',
      package: 'prepay_id=wx_prepay_real',
      signType: 'RSA',
      paySign: 'real_rsa_sign'
    }

    wx.requestPayment.mockImplementation(function (opts) {
      // Verify correct mapping
      expect(opts.timeStamp).toBe(signParams.timeStamp)
      expect(opts.nonceStr).toBe(signParams.nonceStr)
      expect(opts.package).toBe(signParams.package)
      expect(opts.signType).toBe('RSA')
      expect(opts.paySign).toBe(signParams.paySign)
      opts.success({ errMsg: 'requestPayment:ok' })
    })

    const payResult = {
      payment_id: 'p3',
      provider: 'wechat',
      prepay_id: 'wx_prepay_real',
      sign_params: signParams,
      mock_success: false
    }

    const result = await requestWechatPayment(payResult)
    expect(result.success).toBe(true)
    expect(wx.requestPayment).toHaveBeenCalledTimes(1)
  })

  // Test: user cancel is detected
  test('user cancel is reported with cancelled flag', async () => {
    wx.requestPayment.mockImplementation(function (opts) {
      opts.fail({ errMsg: 'requestPayment:fail cancel' })
    })

    const payResult = {
      payment_id: 'p4',
      provider: 'wechat',
      sign_params: {
        appId: 'wx_app',
        timeStamp: '1700000002',
        nonceStr: 'nonce_abc',
        package: 'prepay_id=wx_prepay_abc',
        signType: 'RSA',
        paySign: 'sign_abc'
      },
      mock_success: false
    }

    try {
      await requestWechatPayment(payResult)
      throw new Error('should not reach here')
    } catch (err) {
      expect(err.cancelled).toBe(true)
    }
  })

  // Test: payment failure (non-cancel)
  test('payment failure rejects with cancelled=false', async () => {
    wx.requestPayment.mockImplementation(function (opts) {
      opts.fail({ errMsg: 'requestPayment:fail system error' })
    })

    const payResult = {
      payment_id: 'p5',
      provider: 'wechat',
      sign_params: {
        appId: 'wx_app',
        timeStamp: '1700000003',
        nonceStr: 'nonce_def',
        package: 'prepay_id=wx_prepay_def',
        signType: 'RSA',
        paySign: 'sign_def'
      },
      mock_success: false
    }

    try {
      await requestWechatPayment(payResult)
      throw new Error('should not reach here')
    } catch (err) {
      expect(err.cancelled).toBe(false)
    }
  })

  // Test: missing sign_params rejects
  test('missing sign_params rejects with error message', async () => {
    const payResult = {
      payment_id: 'p6',
      provider: 'wechat',
      sign_params: null,
      mock_success: false
    }

    try {
      await requestWechatPayment(payResult)
      throw new Error('should not reach here')
    } catch (err) {
      expect(err.errMsg).toContain('Missing sign_params')
    }
  })

  // Test: signType defaults to RSA when not provided
  test('signType defaults to RSA when not provided in sign_params', async () => {
    wx.requestPayment.mockImplementation(function (opts) {
      expect(opts.signType).toBe('RSA')
      opts.success({ errMsg: 'requestPayment:ok' })
    })

    const payResult = {
      payment_id: 'p7',
      provider: 'wechat',
      sign_params: {
        appId: 'wx_app',
        timeStamp: '1700000004',
        nonceStr: 'nonce_ghi',
        package: 'prepay_id=wx_prepay_ghi',
        paySign: 'sign_ghi'
      },
      mock_success: false
    }

    await requestWechatPayment(payResult)
    expect(wx.requestPayment).toHaveBeenCalledTimes(1)
  })
})

describe('payOrder + requestWechatPayment integration', () => {
  // Test: full flow - payOrder returns data that requestWechatPayment can consume
  test('payOrder response feeds into requestWechatPayment for mock', async () => {
    const backendResponse = {
      payment_id: 'uuid-123',
      provider: 'mock',
      prepay_id: 'mock_prepay_456',
      sign_params: {
        appId: 'wx_mock',
        timeStamp: '1700000005',
        nonceStr: 'nonce_jkl',
        package: 'prepay_id=mock_prepay_456',
        signType: 'RSA',
        paySign: 'mock_sign_jkl'
      },
      mock_success: true
    }

    __mockWxRequest(200, backendResponse)
    const payResult = await payOrder('order1')
    const wpResult = await requestWechatPayment(payResult)
    expect(wpResult.success).toBe(true)
    expect(wpResult.mock).toBe(true)
  })
})
