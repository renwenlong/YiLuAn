#!/usr/bin/env node
/**
 * S3-TEST-003-A11Y-CERT-FIELDS — tester-owned a11y contract gate.
 *
 * This is intentionally static/semantic instead of miniprogram-automator:
 * - CI/WSL can run it without WeChat DevTools GUI.
 * - It locks the AC#5 contract that matters for screen readers, color-only
 *   status regressions, and focus traps in the cert-card component.
 */

const fs = require('fs')
const path = require('path')
const assert = require('assert')

const repo = path.resolve(__dirname, '..', '..')
const wxmlPath = path.join(repo, 'wechat/components/cert-card/index.wxml')
const jsPath = path.join(repo, 'wechat/components/cert-card/index.js')
const swiftPath = path.join(repo, 'ios/YiLuAn/Features/Precheck/Views/OrderPrecheckSummaryView.swift')

function read(file) {
  return fs.readFileSync(file, 'utf8')
}

function stripComments(text) {
  return text
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '')
    .replace(/^\s*\*.*$/gm, '')
}

function mustContain(text, needle, label) {
  assert(text.includes(needle), `${label} missing: ${needle}`)
}

function mustMatch(text, regex, label) {
  assert(regex.test(text), `${label} missing pattern: ${regex}`)
}

function failIfMatch(text, regex, label) {
  assert(!regex.test(text), `${label} forbidden pattern matched: ${regex}`)
}

function expectThrows(fn, label) {
  let thrown = false
  try {
    fn()
  } catch (_) {
    thrown = true
  }
  assert(thrown, `${label} should fail but passed`)
}

function assertNoProofImageActiveReference(activeText, label) {
  failIfMatch(
    activeText,
    /\b(?:companion_cert_)?proof_image_urls\b/u,
    label
  )
}

const wxml = read(wxmlPath)
const js = read(jsPath)
const swift = read(swiftPath)
const wxmlNoComments = stripComments(wxml)
const jsNoComments = stripComments(js)

// 微信：根 group + card summary + state/field/hint labels must be readable.
//
// I18N-DEV-002B(dafb690) 起 aria-label 全部 i18n 化：不再硬编码中文字面量，
// 改为 {{ariaXxx}}(index.js 经 i18n.t 计算) 或 {{t['certCard.xxx']}}(模板直取)。
// 契约随之从「验中文原文存在」升级为「验 i18n 绑定 + 字典双语非空」——
// 英文读屏用户需要英文 aria-label，锁死中文字面量是无障碍缺陷。
// 非文案语义契约(aria-role / 阅读顺序 / color-only / focus trap / proof 泄漏)不动。
mustContain(wxml, 'aria-role="group"', 'wechat cert-card root role')
mustContain(wxml, 'aria-label="{{a11yLabel}}"', 'wechat cert-card root a11y label')
mustContain(wxml, 'aria-role="status"', 'wechat status/hint aria role')

// 微信：aria-label 必须走 i18n 绑定（{{ariaXxx}} 或 {{t['certCard.xxx']}}），不得留中文字面量。
const wxmlAriaBindings = [
  '{{ariaHeaderLabel}}',
  '{{ariaBadgeVerified}}',
  '{{ariaBadgePending}}',
  '{{ariaBadgeUnverified}}',
  '{{ariaName}}',
  '{{ariaWorkId}}',
  '{{ariaQualifications}}',
  '{{ariaVerifiedAt}}',
  "{{t['certCard.ariaPendingHint']}}",
  "{{t['certCard.ariaUnverifiedHint']}}",
]
for (const binding of wxmlAriaBindings) {
  mustContain(wxml, `aria-label="${binding}"`, `wechat i18n aria-label binding ${binding}`)
}

// 微信：aria-label 内不得残留硬编码中文（i18n 化后应零中文字面量出现在 aria-label 属性值里）。
const ariaLabelValues = [...wxmlNoComments.matchAll(/aria-label="([^"]*)"/gu)].map((m) => m[1])
for (const val of ariaLabelValues) {
  failIfMatch(val, /[\u4e00-\u9fff]/u, `wechat aria-label hardcoded CN residual: "${val}"`)
}

// 微信：index.js 的 aria* 计算属性必须经 i18n.t 派生（不得回填中文常量）。
for (const ariaProp of ['ariaHeaderLabel', 'ariaBadgeVerified', 'ariaBadgePending', 'ariaBadgeUnverified', 'ariaName', 'ariaWorkId', 'ariaQualifications', 'ariaVerifiedAt']) {
  mustMatch(js, new RegExp(`${ariaProp}\\s*:\\s*i18n\\.t\\(`, 'u'), `wechat aria prop ${ariaProp} derived via i18n.t`)
}

// 微信：字典 certCard aria/state key 必须中英双语非空（无孤儿 key / 无缺译）。
const dictPath = path.join(repo, 'wechat/utils/i18n.dict.js')
delete require.cache[require.resolve(dictPath)]
const dictMod = require(dictPath)
const dictRoot = dictMod.dict || dictMod.default || dictMod
const certCardDict = (dictRoot && dictRoot.certCard) || {}
const requiredCertCardKeys = [
  'ariaHeader', 'ariaBadge', 'ariaName', 'ariaWorkId', 'ariaQualifications', 'ariaVerifiedAt',
  'ariaPendingHint', 'ariaUnverifiedHint', 'a11yLabelSuffix',
  'stateVerified', 'statePending', 'stateUnverified',
  'title', 'labelName', 'labelWorkId', 'labelQualifications', 'labelVerifiedAt',
]
for (const key of requiredCertCardKeys) {
  const entry = certCardDict[key]
  assert(entry && typeof entry === 'object', `dict certCard.${key} missing`)
  assert(entry['zh-Hans'] && String(entry['zh-Hans']).trim(), `dict certCard.${key} zh-Hans empty`)
  assert(entry.en && String(entry.en).trim(), `dict certCard.${key} en empty`)
}

// 微信：阅读顺序应与视觉顺序一致：状态 -> 姓名 -> 工号 -> 资质 -> 认证时间。
const orderNeedles = [
  'cert-card__badge',
  'cert-pseudonym-name',
  'cert-work-id',
  'cert-qualifications',
  'cert-verified-at',
]
let cursor = -1
for (const needle of orderNeedles) {
  const idx = wxml.indexOf(needle)
  assert(idx > cursor, `wechat reading order regression around ${needle}`)
  cursor = idx
}

// 微信：cert-card 是只读信息组，不应引入按钮/点击 handler/focus trap。
failIfMatch(wxmlNoComments, /bind(?:tap|longpress|touchstart|touchend)=/u, 'wechat unexpected interactive handler')
failIfMatch(wxmlNoComments, /<button\b/u, 'wechat unexpected button')
failIfMatch(wxmlNoComments, /focus\s*=|auto-focus\s*=/u, 'wechat unexpected focus directive')

// 微信：状态不能只靠颜色；必须有可见状态文字（i18n 化后走 {{t['certCard.stateXxx']}} 绑定），
// 且 state helper 经 i18n.t 派生（非硬编码中文）。
for (const stateKey of ['stateVerified', 'statePending', 'stateUnverified']) {
  mustContain(wxmlNoComments, `>{{t['certCard.${stateKey}']}}</view>`, `wechat visible state text binding ${stateKey}`)
}
mustMatch(js, /i18n\.t\('certCard\.stateVerified'\)/u, 'wechat state helper stateVerified via i18n.t')
mustMatch(js, /i18n\.t\('certCard\.statePending'\)/u, 'wechat state helper statePending via i18n.t')
mustMatch(js, /i18n\.t\('certCard\.stateUnverified'\)/u, 'wechat state helper stateUnverified via i18n.t')

// 微信：证件原图非展示提示 i18n 化为 certCard.a11yLabelSuffix，字典双语非空已在上面 required key 覆盖。

// 微信：不得把 proof image URL 渲染进模板或 computed label。
// Important: do not sanitize the forbidden field before matching. A previous
// version removed `companion_cert_proof_image_urls` first, which let an active
// helper leak pass undetected. The mutation self-tests below lock fail-closed
// behavior for both exact and suffix forms.
assertNoProofImageActiveReference(wxmlNoComments, 'wechat WXML proof image url render')
assertNoProofImageActiveReference(jsNoComments, 'wechat active proof image url reference')

expectThrows(
  () => assertNoProofImageActiveReference(
    'function leak(cs) { var leakedProof = cs && cs.companion_cert_proof_image_urls }',
    'mutation exact proof image field'
  ),
  'mutation self-test: active companion_cert_proof_image_urls reference'
)
expectThrows(
  () => assertNoProofImageActiveReference(
    'function leak(cs) { var leakedProof = cs && cs.proof_image_urls }',
    'mutation suffix proof image field'
  ),
  'mutation self-test: active proof_image_urls reference'
)

// iOS：VoiceOver label/hint must combine card and include cert fields / non-color state.
mustContain(swift, 'PrecheckAccessibilityText.companionCertAccessibilityLabel', 'iOS cert accessibility label hook')
mustContain(swift, 'PrecheckAccessibilityText.companionCertAccessibilityHint', 'iOS cert accessibility hint hook')
mustContain(swift, '.accessibilityElement(children: .combine)', 'iOS combined card accessibility element')
mustContain(swift, '.accessibilityLabel(accessibilityLabel ??', 'iOS accessibility label application')
mustContain(swift, '.accessibilityHint(', 'iOS accessibility hint application')
mustContain(swift, '姓名未提供', 'iOS missing pseudonym semantics')
mustContain(swift, '工号未提供', 'iOS missing work id semantics')
mustContain(swift, '资质未提供', 'iOS missing qualification semantics')
mustContain(swift, '认证时间待核验', 'iOS pending verified-at semantics')
mustContain(swift, '证件原图不会在用户端展示', 'iOS proof image non-display hint')
mustContain(swift, '当前状态不只依赖颜色提示', 'iOS non-color status hint')
mustContain(swift, 'Text("已就绪")', 'iOS visible ready state text')
mustContain(swift, 'Text("未就绪")', 'iOS visible not-ready state text')

console.log('[cert-card-a11y-contract] PASS — WeChat + iOS cert-card a11y contract holds')
