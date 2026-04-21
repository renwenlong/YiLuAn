/**
 * 法律协议元信息（权威源）—— 涵盖隐私政策 + 用户协议
 *
 * ⚠️ 修改隐私文案 / 用户协议正文时，请同步更新此文件中的对应字段，
 *    线上展示页（pages/legal/privacy、pages/legal/terms）会自动绑定，
 *    不要再在 wxml 中硬编码日期 / 版本号。
 *
 * 历史：A21-06 引入 config/privacy.js 仅承载 PRIVACY_*；本次 [B4]
 *      统一扩展为 config/legal.js，新增 TERMS_* 与版本号字段，
 *      原 config/privacy.js 保留为 re-export shim 以兼容历史 require。
 */

// ── 隐私政策 ──────────────────────────────────────────────
// 最近一次更新日期（展示给用户看的字符串，YYYY年M月D日）
const PRIVACY_UPDATED_AT = '2026年4月10日'
// 生效日期（首次上线 / 重大版本生效日）
const PRIVACY_EFFECTIVE_AT = '2026年4月10日'
// 版本号（与 wxml 末尾「v1.0 · 生效日期 …」展示位绑定）
const PRIVACY_VERSION = 'v1.0'

// ── 用户协议 ──────────────────────────────────────────────
// 最近一次更新日期
const TERMS_UPDATED_AT = '2026年4月10日'
// 生效日期
const TERMS_EFFECTIVE_AT = '2026年4月10日'
// 版本号
const TERMS_VERSION = 'v1.0'

module.exports = {
  PRIVACY_UPDATED_AT,
  PRIVACY_EFFECTIVE_AT,
  PRIVACY_VERSION,
  TERMS_UPDATED_AT,
  TERMS_EFFECTIVE_AT,
  TERMS_VERSION,
}
