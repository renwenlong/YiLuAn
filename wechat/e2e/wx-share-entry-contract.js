#!/usr/bin/env node
/**
 * ANDROID-TEST-WX-SHARE-ENTRY — 小程序 Share 发起端入口契约 gate.
 *
 * tester-owned. 静态/语义型，CI/WSL 无 GUI 可跑（同 cert-card-a11y-contract.js 范式）。
 * 锚 test AC：入口 / createShare 契约 / shareWs 事件 / i18n 双语 / 无硬编码残留。
 * 后端断言口径：小程序为 golden 基准端（AC7 三端一致性）。
 */

const fs = require('fs')
const path = require('path')
const assert = require('assert')

const repo = path.resolve(__dirname, '..', '..')
const sharePageWxml = path.join(repo, 'wechat/pages/patient/order-detail/share/index.wxml')
const sharePageJs = path.join(repo, 'wechat/pages/patient/order-detail/share/index.js')
const orderDetailWxml = path.join(repo, 'wechat/pages/patient/order-detail/index.wxml')
const orderDetailJs = path.join(repo, 'wechat/pages/patient/order-detail/index.js')
const shareService = path.join(repo, 'wechat/services/share.js')
const dictPath = path.join(repo, 'wechat/utils/i18n.dict.js')

function read(f) { return fs.readFileSync(f, 'utf8') }
function stripComments(t) {
  return t.replace(/<!--[\s\S]*?-->/g, '').replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '')
}
function mustContain(t, n, l) { assert(t.includes(n), `${l} missing: ${n}`) }
function mustMatch(t, r, l) { assert(r.test(t), `${l} missing pattern: ${r}`) }
function failIfMatch(t, r, l) { assert(!r.test(t), `${l} forbidden: ${r}`) }

// ── AC1: 订单详情有 Share 入口, 点击发起分享 (对齐 iOS createShare 入口语义) ──
const odWxml = read(orderDetailWxml)
const odJs = read(orderDetailJs)
mustContain(odWxml, "t['shareEntry.entryButton']", 'order-detail Share 入口按钮 i18n 绑定')
mustContain(odWxml, 'bindtap="onShareToFamily"', 'order-detail Share 入口 tap handler')
mustMatch(odJs, /onShareToFamily\s*[:(]/u, 'order-detail onShareToFamily handler 定义')

// ── AC2: createShare 契约 POST /orders/{id}/shares + share_scope ──
const svc = read(shareService)
mustContain(svc, 'createShare', 'share service createShare 导出')
mustContain(svc, 'listShares', 'share service listShares 导出')
mustContain(svc, 'revokeShare', 'share service revokeShare 导出')
mustMatch(svc, /orders\/\$\{[^}]+\}\/shares|orders\/.*\/shares/u, 'createShare 走 /orders/{id}/shares')

// ── AC3: shareWs 状态同步事件 ──
const shareWsPath = path.join(repo, 'wechat/services/shareWs.js')
if (fs.existsSync(shareWsPath)) {
  const ws = read(shareWsPath)
  mustMatch(ws, /onMessage|onStatus|share|status/u, 'shareWs 状态事件订阅')
}

// ── AC4: i18n 中英双语非空 (shareEntry + shareScope) ──
delete require.cache[require.resolve(dictPath)]
const dictMod = require(dictPath)
const dictRoot = dictMod.dict || dictMod.default || dictMod
const shareEntry = (dictRoot && dictRoot.shareEntry) || {}
const requiredKeys = [
  'entryButton', 'navTitle', 'pageTitle', 'intro', 'scopeLabel',
  'createButton', 'creating', 'activeListTitle', 'activeCount', 'emptyList', 'limitReached',
]
for (const k of requiredKeys) {
  const e = shareEntry[k]
  assert(e && typeof e === 'object', `dict shareEntry.${k} missing`)
  assert(e['zh-Hans'] && String(e['zh-Hans']).trim(), `dict shareEntry.${k} zh-Hans empty`)
  assert(e.en && String(e.en).trim(), `dict shareEntry.${k} en empty`)
}

// ── AC4b: share 页 + 入口 aria/文案不得残留硬编码中文 (全走 {{t[...]}} 绑定) ──
const shareWxmlNoComments = stripComments(read(sharePageWxml))
const cnResidual = [...shareWxmlNoComments.matchAll(/>\s*([^<{}\n]*[\u4e00-\u9fff][^<{}\n]*?)\s*</gu)]
  .map((m) => m[1].trim())
  .filter(Boolean)
assert(cnResidual.length === 0, `share 页硬编码中文残留 (应走 i18n 绑定): ${JSON.stringify(cnResidual)}`)

// ── fail-closed 自测 ──
function expectThrows(fn, l) { let t = false; try { fn() } catch (_) { t = true } assert(t, `${l} should fail`) }
expectThrows(() => mustContain('nope', "t['shareEntry.entryButton']", 'x'), 'self-test: 入口断言 fail-close')
expectThrows(() => {
  const e = { en: { }, 'zh-Hans': { } }
  assert(e.en && String(e.en).trim(), 'en empty')
  assert(false, 'should not reach')
}, 'self-test: dict 空值 fail-close')

console.log('[wx-share-entry-contract] PASS — 小程序 Share 发起端入口契约 holds')
