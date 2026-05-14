/**
 * sanitizeText — 用户可见文案的统一清洗工具。
 *
 * 后端返回的错误文案会直接进 `wx.showModal({content})`。即便小程序 wxml
 * 自带转义、不会执行 JS，仍有两类风险：
 *   1. 控制字符（\\x00-\\x1F 等）在不同终端渲染异常，可能撑破弹窗布局；
 *   2. 后端被拖库 / 回放攻击 / 文案接口被改时，可超长文案做"社工短信式"
 *      钓鱼（"您的账户已冻结，请添加客服微信 12345 ..."）。
 *
 * 本函数做两件事：
 *   - 剥离 ASCII 控制字符（保留换行 \\n / 制表 \\t 以维持必要排版）
 *   - 截断到 maxLen（默认 200 字），尾部加 ……
 *
 * 不做：HTML 转义（小程序 text 会自动 escape）、敏感词过滤（业务侧负责）。
 */

const DEFAULT_MAX_LEN = 200
const ELLIPSIS = '……'

function sanitizeText(input, options) {
  const maxLen = (options && options.maxLen) || DEFAULT_MAX_LEN
  if (input == null) return ''
  let s = typeof input === 'string' ? input : String(input)

  // 1. 剥控制字符 (\x00-\x08, \x0B-\x0C, \x0E-\x1F, \x7F)，保留 \n \t \r
  // eslint-disable-next-line no-control-regex
  s = s.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, '')

  // 2. 折叠连续空白（避免 "title\n\n\n\n\n\n payload" 撑高弹窗），
  //    最多保留两个连续换行。
  s = s.replace(/\n{3,}/g, '\n\n')

  // 3. 截断
  if (s.length > maxLen) {
    s = s.slice(0, maxLen) + ELLIPSIS
  }

  return s
}

module.exports = {
  sanitizeText: sanitizeText,
  DEFAULT_MAX_LEN: DEFAULT_MAX_LEN,
}
