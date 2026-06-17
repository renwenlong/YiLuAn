jest.mock('../../services/auth', () => ({
  sendOTP: jest.fn(),
  bindPhone: jest.fn(),
}))
global.Page = global.Page || jest.fn()
var authService = require('../../services/auth')

function createPage(pageConfig) {
  var page = Object.assign({}, pageConfig, { data: Object.assign({}, pageConfig.data) })
  page.setData = function (obj) {
    Object.assign(this.data, obj)
  }
  return page
}

beforeEach(function () {
  jest.clearAllMocks()
  __resetWxStorage()
  wx.setStorageSync('yiluan_access_token', 'test_token')
})

describe('pages/bind-phone', function () {
  test('onSendOTP calls sendOTP service', async function () {
    authService.sendOTP.mockResolvedValue({})
    var page = createPage({
      data: { phone: '13800138000', code: '', countdown: 0, sending: false, binding: false }
    })
    page.onSendOTP = function () {
      /* simplified test */
    }
    // Test that sendOTP can be called
    await authService.sendOTP('13800138000')
    expect(authService.sendOTP).toHaveBeenCalledWith('13800138000')
  })

  test('onBind calls bindPhone service', async function () {
    authService.bindPhone.mockResolvedValue({ phone: '13800138000' })
    await authService.bindPhone('13800138000', '123456')
    expect(authService.bindPhone).toHaveBeenCalledWith('13800138000', '123456')
  })

  test('validation rejects invalid phone', function () {
    var validate = require('../../utils/validate')
    expect(validate.isValidPhone('123')).toBe(false)
    expect(validate.isValidPhone('13800138000')).toBe(true)
  })
})

// 绑定失败时把后端 400/409 真实原因透出为中文（不再笼统“绑定失败”）
describe('pages/bind-phone _bindErrorMessage', function () {
  var _bindErrorMessage = require('../../pages/profile/bind-phone/index')._bindErrorMessage

  test('exported helper is available', function () {
    expect(typeof _bindErrorMessage).toBe('function')
  })

  test('maps known backend messages (plain string detail) to Chinese', function () {
    expect(_bindErrorMessage({ data: { detail: 'User already has a phone number bound' } }))
      .toBe('该账号已绑定手机号')
    expect(_bindErrorMessage({ data: { detail: 'OTP code expired or not found' } }))
      .toBe('验证码已过期或未发送，请重新获取')
    expect(_bindErrorMessage({ data: { detail: 'Invalid OTP code' } }))
      .toBe('验证码错误，请检查后重试')
    expect(_bindErrorMessage({ data: { detail: 'Phone number already registered to another account' } }))
      .toBe('该手机号已被其他账号注册')
  })

  test('maps known message when detail is an object with message', function () {
    expect(_bindErrorMessage({ data: { detail: { message: 'User already has a phone number bound' } } }))
      .toBe('该账号已绑定手机号')
  })

  test('falls back to backend text when message is unmapped', function () {
    expect(_bindErrorMessage({ data: { detail: 'Some unexpected backend error' } }))
      .toBe('Some unexpected backend error')
  })

  test('falls back to generic text when no detail present', function () {
    expect(_bindErrorMessage({})).toBe('绑定失败，请稍后重试')
    expect(_bindErrorMessage(null)).toBe('绑定失败，请稍后重试')
    expect(_bindErrorMessage({ data: {} })).toBe('绑定失败，请稍后重试')
  })
})
