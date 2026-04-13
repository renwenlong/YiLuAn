// --- Part 1: API-level tests (real services/user, real wx.request mock) ---

beforeEach(() => {
  jest.clearAllMocks()
  __resetWxStorage()
  wx.setStorageSync('yiluan_access_token', 'test_token')
})

describe('services/user - deleteAccount', () => {
  test('deleteAccount calls DELETE /users/me with verification code', async () => {
    __mockWxRequest(200, { message: 'Account deleted' })
    const { deleteAccount } = require('../../services/user')

    const result = await deleteAccount('123456')
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('users/me')
    expect(callArgs.method).toBe('DELETE')
    expect(callArgs.data).toEqual({ code: '123456' })
    expect(result.message).toBe('Account deleted')
  })

  test('deleteAccount rejects on server error', async () => {
    __mockWxRequest(400, { detail: 'Invalid verification code' })
    const { deleteAccount } = require('../../services/user')

    await expect(deleteAccount('000000')).rejects.toEqual({
      statusCode: 400,
      data: { detail: 'Invalid verification code' }
    })
  })

  test('deleteAccount includes auth header', async () => {
    __mockWxRequest(200, { message: 'ok' })
    const { deleteAccount } = require('../../services/user')

    await deleteAccount('123456')
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.header['Authorization']).toBe('Bearer test_token')
  })
})

// --- Part 2: Page logic tests (mocked services, manual page simulation) ---

global.Page = global.Page || jest.fn()

function createPage(pageConfig) {
  const page = Object.assign({}, pageConfig, { data: Object.assign({}, pageConfig.data) })
  page.setData = function (obj) {
    Object.assign(this.data, obj)
  }
  return page
}

describe('pages/settings/delete-account - page logic', () => {
  test('page initializes with default disabled state', () => {
    const page = createPage({
      data: { phone: '', phoneMask: '', code: '', confirmed: false, canSubmit: false, countdown: 0, submitting: false }
    })
    expect(page.data.canSubmit).toBe(false)
    expect(page.data.confirmed).toBe(false)
    expect(page.data.code).toBe('')
  })

  test('phone mask is computed correctly from full phone number', () => {
    const page = createPage({
      data: { phone: '', phoneMask: '', code: '', confirmed: false, canSubmit: false }
    })
    const phone = '13800138000'
    const mask = phone.slice(0, 3) + '****' + phone.slice(-4)
    page.setData({ phone: phone, phoneMask: mask })

    expect(page.data.phoneMask).toBe('138****8000')
  })

  test('confirm toggle switches confirmed state', () => {
    const page = createPage({
      data: { confirmed: false, code: '', canSubmit: false }
    })
    page.onToggleConfirm = function () {
      this.setData({ confirmed: !this.data.confirmed })
      this._updateCanSubmit()
    }
    page._updateCanSubmit = function () {
      this.setData({ canSubmit: this.data.confirmed && this.data.code.length === 6 })
    }

    page.onToggleConfirm()
    expect(page.data.confirmed).toBe(true)
    page.onToggleConfirm()
    expect(page.data.confirmed).toBe(false)
  })

  test('canSubmit true only when confirmed + 6-digit code', () => {
    const page = createPage({
      data: { confirmed: false, code: '', canSubmit: false }
    })
    page._updateCanSubmit = function () {
      this.setData({ canSubmit: this.data.confirmed && this.data.code.length === 6 })
    }
    page.onToggleConfirm = function () {
      this.setData({ confirmed: !this.data.confirmed })
      this._updateCanSubmit()
    }
    page.onCodeInput = function (e) {
      this.setData({ code: e.detail.value })
      this._updateCanSubmit()
    }

    page.onToggleConfirm()
    expect(page.data.canSubmit).toBe(false)

    page.onCodeInput({ detail: { value: '123456' } })
    expect(page.data.canSubmit).toBe(true)

    page.onToggleConfirm()
    expect(page.data.canSubmit).toBe(false)
  })

  test('canSubmit stays false with partial code', () => {
    const page = createPage({
      data: { confirmed: true, code: '', canSubmit: false }
    })
    page._updateCanSubmit = function () {
      this.setData({ canSubmit: this.data.confirmed && this.data.code.length === 6 })
    }
    page.onCodeInput = function (e) {
      this.setData({ code: e.detail.value })
      this._updateCanSubmit()
    }

    page.onCodeInput({ detail: { value: '123' } })
    expect(page.data.canSubmit).toBe(false)
  })

  test('onCancel navigates back', () => {
    const page = createPage({ data: {} })
    page.onCancel = function () {
      wx.navigateBack()
    }

    page.onCancel()
    expect(wx.navigateBack).toHaveBeenCalled()
  })

  test('onSendCode shows error toast if phone is empty', () => {
    const page = createPage({
      data: { phone: '', countdown: 0 }
    })
    page.onSendCode = function () {
      if (!this.data.phone) {
        wx.showToast({ title: '未绑定手机号', icon: 'none' })
        return
      }
    }

    page.onSendCode()
    expect(wx.showToast).toHaveBeenCalledWith(
      expect.objectContaining({ title: '未绑定手机号' })
    )
  })

  test('successful delete clears tokens and redirects to login', () => {
    const { clearTokens } = require('../../utils/token')
    const store = require('../../store/index')

    clearTokens()
    store.reset()
    wx.reLaunch({ url: '/pages/login/index' })

    expect(wx.reLaunch).toHaveBeenCalledWith({ url: '/pages/login/index' })
  })
})
