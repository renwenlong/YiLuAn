// scripts/scan-hardcoded-cn.js
// I18N-DEV-002 AC-7 — 残留中文静态扫描
//
// 扫 wxml + js（View 层）里未抽 key 的硬编码中文，输出清单。
// 白名单排除：注释、品牌名、i18n 字典本身、测试、生成文件。
// 用途：① 量化 AC-3 抽 key 工作量 ② TEST-002 回归跑（English 下应无残留）。
//
// 用法：node scripts/scan-hardcoded-cn.js [--json]
// 退出码：有残留=1，无残留=0（供 CI/测试 gate）。

const fs = require('fs')
const path = require('path')

const ROOT = path.resolve(__dirname, '..')

const SCAN_DIRS = ['pages', 'components', 'behaviors']
const SCAN_EXT = ['.wxml', '.js']

const SKIP_PATH = [
  'node_modules', '__tests__', '.test.js',
  'utils/i18n.dict.js', 'utils/i18n.js',
  'scripts/', 'utils/constants.js',
  // AC-3 边界裁决 (凝光 PM 2026-07-10 拍板, PRD 751536c):
  // 法律条款正文本期不译 (合规风险需法务审校, 非 UI 范围).
  'pages/legal/privacy/', 'pages/legal/terms/',
]

const ALLOW_TOKENS = ['\u533b\u8def\u5b89'] // 医路安 品牌名

const CN = /[\u4e00-\u9fff]/

function shouldSkipFile(rel) {
  return SKIP_PATH.some((s) => rel.indexOf(s) !== -1)
}

function stripComments(line, ext) {
  let s = line
  if (ext === '.js') {
    s = s.replace(/\/\/.*$/, '')
    s = s.replace(/\/\*.*?\*\//g, '')
  }
  s = s.replace(/<!--.*?-->/g, '')
  return s
}

// 先在整份文件上 strip 跨行块注释，用等量换行替换以保持行号对齐。
// 逐行 stripComments 无法处理跨 /* ... */ 与 <!-- ... --> 块，会误报注释中文。
function stripBlockComments(text, ext) {
  const replaceKeepLines = (src, re) =>
    src.replace(re, (m) => m.replace(/[^\n]/g, ' '))
  let s = text
  if (ext === '.js') s = replaceKeepLines(s, /\/\*[\s\S]*?\*\//g)
  s = replaceKeepLines(s, /<!--[\s\S]*?-->/g)
  return s
}

function isAllowed(line) {
  const stripped = ALLOW_TOKENS.reduce((acc, t) => acc.split(t).join(''), line)
  return !CN.test(stripped)
}

function walk(dir, out) {
  let entries
  try { entries = fs.readdirSync(dir, { withFileTypes: true }) } catch (e) { return }
  for (const e of entries) {
    const full = path.join(dir, e.name)
    const rel = path.relative(ROOT, full)
    if (shouldSkipFile(rel)) continue
    if (e.isDirectory()) {
      walk(full, out)
    } else if (SCAN_EXT.indexOf(path.extname(e.name)) !== -1) {
      out.push(full)
    }
  }
}

function scan() {
  const files = []
  for (const d of SCAN_DIRS) walk(path.join(ROOT, d), files)
  const hits = []
  for (const f of files) {
    const rel = path.relative(ROOT, f)
    const ext = path.extname(f)
    const lines = stripBlockComments(fs.readFileSync(f, 'utf8'), ext).split('\n')
    for (let i = 0; i < lines.length; i++) {
      const stripped = stripComments(lines[i], ext)
      if (CN.test(stripped) && !isAllowed(stripped)) {
        hits.push({ file: rel, line: i + 1, text: lines[i].trim().slice(0, 80) })
      }
    }
  }
  return hits
}

const hits = scan()
const asJson = process.argv.indexOf('--json') !== -1

if (asJson) {
  console.log(JSON.stringify({ count: hits.length, hits }, null, 2))
} else {
  const byFile = {}
  for (const h of hits) { byFile[h.file] = (byFile[h.file] || 0) + 1 }
  console.log('[scan-hardcoded-cn] residual hardcoded CN lines:', hits.length)
  console.log('[scan-hardcoded-cn] files involved:', Object.keys(byFile).length)
  Object.keys(byFile).sort((a, b) => byFile[b] - byFile[a]).slice(0, 30).forEach((f) => {
    console.log('  ' + String(byFile[f]).padStart(4) + '  ' + f)
  })
}

process.exit(hits.length > 0 ? 1 : 0)
