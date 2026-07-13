#!/usr/bin/env node
// ios/scripts/gen-xcstrings.js
// I18N-DEV-003 (ADR-0063 §3.2 / §5.1) — 从主字典 SSoT 生成 iOS String Catalog。
//
// 主字典真源：docs/i18n/dictionary.json（DEV-001 产出，跨端 key 集强制一致）。
// 输出：ios/YiLuAn/Resources/Localizable.xcstrings（String Catalog, zh-Hans + en）。
//
// key 规范（§3.1）：扁平点号 `namespace.key`，与微信 i18n.dict.js 同 key 集。
// 占位转换：主字典具名占位 `{name}` → String Catalog `%@`（位置占位，
//   由 LocalizationManager.t(key, args...) 用 String(format:) 按序填充；
//   调用方保证 args 顺序符合目标语言语序，_params 数组即顺序契约）。
//
// 用法：node ios/scripts/gen-xcstrings.js（仓库根或任意 cwd）。
// 主字典变更后重新生成，随 PR 提交，保证与微信端 key 集一致。

const fs = require('fs')
const path = require('path')

const ROOT = path.resolve(__dirname, '..', '..')
const SSOT = path.join(ROOT, 'docs', 'i18n', 'dictionary.json')
const OUT = path.join(ROOT, 'ios', 'YiLuAn', 'Resources', 'Localizable.xcstrings')

const raw = JSON.parse(fs.readFileSync(SSOT, 'utf8'))

// 具名占位 {name} → %@（按 _params 顺序；无 _params 时按出现顺序）
function toPositional(text, params) {
  if (!params || params.length === 0) {
    // 仍可能含 {x}（防御）：按出现顺序转 %@
    return text.replace(/\{(\w+)\}/g, '%@')
  }
  // 按 _params 声明顺序替换，保证 zh/en 占位顺序一致
  let out = text
  for (const p of params) {
    out = out.split('{' + p + '}').join('%@')
  }
  // 兜底：残留未声明占位也转
  out = out.replace(/\{(\w+)\}/g, '%@')
  return out
}

const strings = {}
let keyCount = 0

for (const ns of Object.keys(raw)) {
  if (ns === '_meta') continue
  const group = raw[ns]
  if (!group || typeof group !== 'object') continue
  for (const key of Object.keys(group)) {
    const entry = group[key]
    if (!entry || typeof entry !== 'object') continue
    const zh = entry['zh-Hans']
    const en = entry['en']
    if (zh == null || en == null) continue
    const params = entry._params || null
    const flatKey = ns + '.' + key
    strings[flatKey] = {
      localizations: {
        'zh-Hans': {
          stringUnit: { state: 'translated', value: toPositional(String(zh), params) },
        },
        en: {
          stringUnit: { state: 'translated', value: toPositional(String(en), params) },
        },
      },
    }
    keyCount++
  }
}

const catalog = {
  sourceLanguage: 'zh-Hans',
  strings,
  version: '1.0',
}

fs.mkdirSync(path.dirname(OUT), { recursive: true })
fs.writeFileSync(OUT, JSON.stringify(catalog, null, 2) + '\n', 'utf8')
console.log('[gen-xcstrings] wrote', OUT)
console.log('[gen-xcstrings] keys:', keyCount)
