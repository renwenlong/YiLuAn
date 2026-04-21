// [B4]: \u9a8c\u8bc1\u7528\u6237\u534f\u8bae\u9875\u9762\u52a8\u6001\u7ed1\u5b9a config/legal.js \u4e2d\u7684\u66f4\u65b0\u65f6\u95f4 / \u751f\u6548\u65e5\u671f / \u7248\u672c\u53f7

const { TERMS_UPDATED_AT, TERMS_EFFECTIVE_AT, TERMS_VERSION } = require('../../config/legal')

const pageDef = (function () {
  var captured = null
  var origPage = global.Page
  global.Page = function (def) { captured = def }
  jest.isolateModules(function () {
    require('../../pages/legal/terms/index')
  })
  global.Page = origPage
  return captured
})()

describe('legal/terms page \u52a8\u6001\u5143\u4fe1\u606f\u7ed1\u5b9a', () => {
  test('config \u4e2d TERMS_UPDATED_AT \u4e0d\u4e3a\u7a7a\u4e14\u4e3a\u5b57\u7b26\u4e32', () => {
    expect(typeof TERMS_UPDATED_AT).toBe('string')
    expect(TERMS_UPDATED_AT.length).toBeGreaterThan(0)
  })

  test('config \u4e2d TERMS_EFFECTIVE_AT \u4e0d\u4e3a\u7a7a\u4e14\u4e3a\u5b57\u7b26\u4e32', () => {
    expect(typeof TERMS_EFFECTIVE_AT).toBe('string')
    expect(TERMS_EFFECTIVE_AT.length).toBeGreaterThan(0)
  })

  test('config \u4e2d TERMS_VERSION \u4ee5 v \u5f00\u5934', () => {
    expect(typeof TERMS_VERSION).toBe('string')
    expect(TERMS_VERSION).toMatch(/^v\d/)
  })

  test('\u9875\u9762 data.updatedAt \u7ed1\u5b9a\u5230 TERMS_UPDATED_AT', () => {
    expect(pageDef).toBeTruthy()
    expect(pageDef.data.updatedAt).toBe(TERMS_UPDATED_AT)
  })

  test('\u9875\u9762 data.effectiveAt \u7ed1\u5b9a\u5230 TERMS_EFFECTIVE_AT', () => {
    expect(pageDef.data.effectiveAt).toBe(TERMS_EFFECTIVE_AT)
  })

  test('\u9875\u9762 data.version \u7ed1\u5b9a\u5230 TERMS_VERSION', () => {
    expect(pageDef.data.version).toBe(TERMS_VERSION)
  })
})

describe('config/privacy shim \u5411\u540e\u517c\u5bb9', () => {
  test('require config/privacy \u4ecd\u53ef\u62ff\u5230 PRIVACY_UPDATED_AT', () => {
    const shim = require('../../config/privacy')
    expect(shim.PRIVACY_UPDATED_AT).toBeTruthy()
    expect(typeof shim.PRIVACY_UPDATED_AT).toBe('string')
  })
})
