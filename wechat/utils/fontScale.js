// fontScale.js
// S2-INT-003 — 巨字号缩放表唯一真源（PRD §F5）
//
// 真源：docs/design/wireframes/U1-folding-stepper/README.md §「巨字号缩放表」
// 双端 token 完整一致（非仅按钮），缩放非等比，逐项取值。
//
// 用法：页面根据是否巨字号模式，setData(fontScale.tokens(huge))，
// wxml 用 style 绑定，或 class 切换。本模块只提供数值真源。

// 缩放表（钉死 · 非等比逐项取值）
var TABLE = {
  // token: [常规, 巨字号]
  bodyFont: [14, 18],        // 正文字号
  metaFont: [12, 15],        // 次要字号（摘要/meta）
  primaryBtnH: [42, 50],     // 主按钮高
  labelMarginTop: [12, 15],  // 行内间距 label 上
  labelMarginBottom: [6, 8], // 行内间距 label 下
  stepNum: [22, 26]          // 步骤头 num 圆点
}

// 摘要行截断：常规单行省略，巨字号两行截断 + 「…」
function summaryClamp(huge) {
  return huge ? 2 : 1
}

// 返回当前模式下的全部 token 数值（px 数字）。
function tokens(huge) {
  var idx = huge ? 1 : 0
  return {
    bodyFont: TABLE.bodyFont[idx],
    metaFont: TABLE.metaFont[idx],
    primaryBtnH: TABLE.primaryBtnH[idx],
    labelMarginTop: TABLE.labelMarginTop[idx],
    labelMarginBottom: TABLE.labelMarginBottom[idx],
    stepNum: TABLE.stepNum[idx],
    summaryClamp: summaryClamp(huge)
  }
}

module.exports = {
  TABLE: TABLE,
  tokens: tokens,
  summaryClamp: summaryClamp
}
