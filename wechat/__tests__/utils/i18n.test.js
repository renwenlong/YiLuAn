// __tests__/utils/i18n.test.js
// I18N-DEV-002 — i18n 运行时单测（AC-1/1.1/2.1/5 逻辑闭环）

const store = require('../../store/index')
const i18n = require('../../utils/i18n')

const ZH_CONFIRM = '\u786e\u8ba4'      // 确认
const ZH_CREATED = '\u5f85\u63a5\u5355' // 待接单

beforeEach(() => {
  store._clearAllListeners()
  global.__resetWxStorage()
  global.wx.getSystemInfoSync = jest.fn(() => ({ language: 'zh_CN' }))
  store.reset()
})

describe('i18n.t', () => {
  test('static key zh', () => {
    store.setState({ language: 'zh-Hans' })
    expect(i18n.t('common.confirm')).toBe(ZH_CONFIRM)
    expect(i18n.t('orderStatus.created')).toBe(ZH_CREATED)
  })

  test('en', () => {
    store.setState({ language: 'en' })
    expect(i18n.t('common.confirm')).toBe('Confirm')
    expect(i18n.t('orderStatus.rejected_by_companion')).toBe('Rejected by Companion')
  })

  test('placeholder {phone}', () => {
    store.setState({ language: 'en' })
    expect(i18n.t('otp.sentTo', { phone: '13800138000' })).toBe('Code sent to +86 13800138000')
  })

  test('missing key fallback', () => {
    store.setState({ language: 'zh-Hans' })
    expect(i18n.t('nonexistent.key')).toBe('nonexistent.key')
  })

  test('refundState.refunded', () => {
    store.setState({ language: 'en' })
    expect(i18n.t('refundState.refunded')).toBe('Refunded')
  })

  test('no phantom in_service / refunded in orderStatus', () => {
    store.setState({ language: 'zh-Hans' })
    expect(i18n.t('orderStatus.in_service')).toBe('orderStatus.in_service')
    expect(i18n.t('orderStatus.refunded')).toBe('orderStatus.refunded')
  })
})

describe('reset() footgun (AC-1.1)', () => {
  test('logout reset keeps language from Storage', () => {
    i18n.setLang('en')
    expect(store.getState().language).toBe('en')
    store.reset()
    expect(store.getState().language).toBe('en')
    expect(i18n.getCurrentLang()).toBe('en')
  })

  test('reset does not falsely fire language selector to default', () => {
    i18n.setLang('en')
    const listener = jest.fn()
    store.subscribeSelector(store.selectLanguage, listener)
    store.reset()
    expect(store.getState().language).toBe('en')
    expect(listener).not.toHaveBeenCalled()
  })

  test('reset with empty Storage -> undefined', () => {
    global.__resetWxStorage()
    store.reset()
    expect(store.getState().language).toBeUndefined()
  })
})

describe('resolveDefaultLang (FR-2)', () => {
  test('Storage priority', () => {
    wx.setStorageSync('language', 'en')
    expect(i18n.resolveDefaultLang()).toBe('en')
  })

  test('no value + zh system -> zh-Hans written back', () => {
    global.__resetWxStorage()
    global.wx.getSystemInfoSync = jest.fn(() => ({ language: 'zh_CN' }))
    expect(i18n.resolveDefaultLang()).toBe('zh-Hans')
    expect(wx.getStorageSync('language')).toBe('zh-Hans')
  })

  test('no value + en system -> en written back', () => {
    global.__resetWxStorage()
    global.wx.getSystemInfoSync = jest.fn(() => ({ language: 'en' }))
    expect(i18n.resolveDefaultLang()).toBe('en')
    expect(wx.getStorageSync('language')).toBe('en')
  })
})

describe('normalizeLang', () => {
  test('zh* -> zh-Hans else en', () => {
    expect(i18n.normalizeLang('zh_CN')).toBe('zh-Hans')
    expect(i18n.normalizeLang('zh-Hant')).toBe('zh-Hans')
    expect(i18n.normalizeLang('en')).toBe('en')
    expect(i18n.normalizeLang('fr')).toBe('en')
    expect(i18n.normalizeLang('')).toBe('zh-Hans')
  })
})

describe('setLang', () => {
  test('writes store + Storage', () => {
    i18n.setLang('en')
    expect(store.getState().language).toBe('en')
    expect(wx.getStorageSync('language')).toBe('en')
  })

  test('invalid ignored', () => {
    i18n.setLang('zh-Hans')
    i18n.setLang('fr')
    expect(store.getState().language).toBe('zh-Hans')
  })
})

describe('buildScopedDict', () => {
  test('scoped flat map current lang', () => {
    store.setState({ language: 'zh-Hans' })
    const d = i18n.buildScopedDict(['common', 'orderStatus'])
    expect(d['common.confirm']).toBe(ZH_CONFIRM)
    expect(d['orderStatus.created']).toBe(ZH_CREATED)
    expect(d['settings.title']).toBeUndefined()
  })

  test('skip placeholder (_params) entries', () => {
    store.setState({ language: 'en' })
    const d = i18n.buildScopedDict(['otp'])
    expect(d['otp.sentTo']).toBeUndefined()
  })
})
