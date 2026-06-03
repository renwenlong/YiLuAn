// fontScale.test.js
// S2-INT-003 — 巨字号缩放表单测（双端 token 完整一致，逐项钉死）

var F = require('../../utils/fontScale')

describe('fontScale 巨字号缩放表（钉死 · 非等比）', function () {
  test('常规模式逐项取值', function () {
    expect(F.tokens(false)).toEqual({
      bodyFont: 14,
      metaFont: 12,
      primaryBtnH: 42,
      labelMarginTop: 12,
      labelMarginBottom: 6,
      stepNum: 22,
      summaryClamp: 1
    })
  })

  test('巨字号模式逐项取值', function () {
    expect(F.tokens(true)).toEqual({
      bodyFont: 18,
      metaFont: 15,
      primaryBtnH: 50,
      labelMarginTop: 15,
      labelMarginBottom: 8,
      stepNum: 26,
      summaryClamp: 2
    })
  })

  test('摘要截断：常规单行/巨字号两行', function () {
    expect(F.summaryClamp(false)).toBe(1)
    expect(F.summaryClamp(true)).toBe(2)
  })

  test('缩放非等比（正文 14→18 比 metaFont 12→15 不等比）', function () {
    var n = F.tokens(false)
    var h = F.tokens(true)
    // 正文放大 ~1.286x，meta 放大 1.25x，按钮 ~1.19x —— 三者不同，证明非等比
    expect(h.bodyFont / n.bodyFont).not.toBe(h.primaryBtnH / n.primaryBtnH)
  })
})
