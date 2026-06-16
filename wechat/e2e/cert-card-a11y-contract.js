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

const wxml = read(wxmlPath)
const js = read(jsPath)
const swift = read(swiftPath)
const wxmlNoComments = stripComments(wxml)
const jsNoComments = stripComments(js)

// 微信：根 group + card summary + state/field/hint labels must be readable.
mustContain(wxml, 'aria-role="group"', 'wechat cert-card root role')
mustContain(wxml, 'aria-label="{{a11yLabel}}"', 'wechat cert-card root a11y label')
mustContain(wxml, 'aria-label="陪诊师资质，状态：{{a11yStateLabel}}"', 'wechat header state label')
mustContain(wxml, 'aria-label="陪诊师资质状态：已认证"', 'wechat verified badge label')
mustContain(wxml, 'aria-label="陪诊师资质状态：临时证明补交中"', 'wechat pending badge label')
mustContain(wxml, 'aria-label="陪诊师资质状态：未认证"', 'wechat unverified badge label')
mustContain(wxml, 'aria-label="陪诊师化名：{{certStatus.companion_cert_pseudonym_name}}"', 'wechat pseudonym row label')
mustContain(wxml, 'aria-label="陪诊师工号：{{certStatus.companion_cert_work_id}}"', 'wechat work id row label')
mustContain(wxml, 'aria-label="陪诊师资质：{{a11yQualifications}}"', 'wechat qualifications row label')
mustContain(wxml, 'aria-label="认证时间：{{verifiedAtDisplay}}"', 'wechat verified-at row label')
mustContain(wxml, 'aria-role="status"', 'wechat status/hint aria role')

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

// 微信：状态不能只靠颜色；必须有可见状态文字 + semantic helper.
for (const visibleState of ['已认证', '临时证明补交中', '未认证']) {
  mustContain(wxmlNoComments, `>${visibleState}</view>`, `wechat visible state text ${visibleState}`)
  mustContain(js, visibleState, `wechat state helper text ${visibleState}`)
}
mustContain(js, '证件原图不会在用户端展示', 'wechat proof image non-display hint')

// 微信：不得把 proof image URL 渲染进模板或 computed label。
failIfMatch(wxmlNoComments, /companion_cert_proof_image_urls/u, 'wechat WXML proof image url render')
const jsActive = jsNoComments.replace(/companion_cert_proof_image_urls/g, '')
failIfMatch(jsActive, /proof_image_urls/u, 'wechat active proof image url reference')

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
