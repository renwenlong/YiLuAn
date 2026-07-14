// scripts/gen-i18n-dict.js
// I18N-DEV-002 — 从主字典 SSoT 生成微信端 CommonJS 镜像 utils/i18n.dict.js
//
// 主字典真源：docs/i18n/dictionary.json（DEV-001 产出）。
// 微信小程序无法 require 仓库根 JSON，故生成本目录 CommonJS 镜像，key 集强制一致。
//
// 用法：node scripts/gen-i18n-dict.js （在 wechat/ 目录下运行）
// 主字典变更后重新生成，随 PR 一并提交，保证两端 key 集一致。

const fs = require('fs')
const path = require('path')

const SSOT = path.resolve(__dirname, '../../docs/i18n/dictionary.json')
const OUT = path.resolve(__dirname, '../utils/i18n.dict.js')

const raw = JSON.parse(fs.readFileSync(SSOT, 'utf8'))

// 去掉 _meta，保留业务 namespace（含 _params/_note，t() 依 _params 判断静态/动态）
const out = {}
for (const k of Object.keys(raw)) {
  if (k === '_meta') continue
  out[k] = raw[k]
}

const header =
  '// utils/i18n.dict.js\n' +
  '// I18N-DEV-002 — 微信端字典镜像（自 docs/i18n/dictionary.json 生成，key 集强制一致）\n' +
  '//\n' +
  '// ⚠ 勿手改此文件。主字典 SSoT = docs/i18n/dictionary.json（DEV-001 产出）。\n' +
  '// 微信小程序无法 require 仓库根 JSON，故本目录维护 CommonJS 镜像。\n' +
  '// 同步方式：node scripts/gen-i18n-dict.js（本期）；主字典变更后重新生成并提交。\n' +
  '\n' +
  'module.exports = '

const body = JSON.stringify(out, null, 2)
fs.writeFileSync(OUT, header + body + '\n', 'utf8')

const nsCount = Object.keys(out).length
let leafCount = 0
for (const ns of Object.keys(out)) {
  const g = out[ns]
  if (g && typeof g === 'object') leafCount += Object.keys(g).length
}
console.log('[gen-i18n-dict] wrote', OUT)
console.log('[gen-i18n-dict] namespaces:', nsCount, '| entries:', leafCount)
