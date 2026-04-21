// A21-06: \u9a8c\u8bc1\u9690\u79c1\u534f\u8bae\u9875\u9762\u52a8\u6001\u7ed1\u5b9a config/privacy.js \u4e2d\u7684\u66f4\u65b0\u65f6\u95f4

const { PRIVACY_UPDATED_AT, PRIVACY_EFFECTIVE_AT } = require('../../config/privacy')

// \u52a0\u8f7d\u9875\u9762\u5b9a\u4e49
const pageDef = (function () {
  var captured = null
  var origPage = global.Page
  global.Page = function (def) { captured = def }
  jest.isolateModules(function () {
    require('../../pages/legal/privacy/index')
  })
  global.Page = origPage
  return captured
})()

describe('legal/privacy page \u52a8\u6001\u66f4\u65b0\u65f6\u95f4', () => {
  test('config \u4e2d PRIVACY_UPDATED_AT \u4e0d\u4e3a\u7a7a\u4e14\u4e3a\u5b57\u7b26\u4e32', () => {
    expect(typeof PRIVACY_UPDATED_AT).toBe('string')
    expect(PRIVACY_UPDATED_AT.length).toBeGreaterThan(0)
  })

  test('\u9875\u9762 data.updatedAt \u7ed1\u5b9a\u5230 PRIVACY_UPDATED_AT', () => {
    expect(pageDef).toBeTruthy()
    expect(pageDef.data.updatedAt).toBe(PRIVACY_UPDATED_AT)
  })

  test('\u9875\u9762 data.effectiveAt \u7ed1\u5b9a\u5230 PRIVACY_EFFECTIVE_AT', () => {
    expect(pageDef.data.effectiveAt).toBe(PRIVACY_EFFECTIVE_AT)
  })

  test('\u6e32\u67d3\u4e0a\u4e0b\u6587\u5e94\u542b\u52a8\u6001\u66f4\u65b0\u65f6\u95f4\u5b57\u6bb5\uff08\u63a8\u5bfc\u6a21\u62df\uff09', () => {
    // wxml \u4e2d\u4f7f\u7528 {{updatedAt}}\uff0c\u6e32\u67d3\u540e\u7b49\u4ef7\u4e8e data.updatedAt
    var rendered = '\u66f4\u65b0\u65e5\u671f\uff1a' + pageDef.data.updatedAt
    expect(rendered).toContain(PRIVACY_UPDATED_AT)
  })
})
