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
]

// AC-3 边界裁决 (凝光 PM 2026-07-10 拍板 PRD 751536c + 魈 CR 2026-07-11):
// 法律页只豁免「正文 body」(协议条款/隐私条款), UI chrome (标题/footer/返回顶部等) 仍抽 t().
// 旧版整目录 SKIP_PATH 会让 chrome 汉字漏扫造假绿, 故降为行级豁免:
// 仅当行含下列正文 body class 时才豁免, 其余行 (chrome) 照扫.
const LEGAL_BODY_PATH = ['pages/legal/privacy/', 'pages/legal/terms/']
const LEGAL_BODY_CLASS = [
  'section-body', 'section-title', 'subsection-title', 'list-item',
]

function isLegalBodyLine(rel, line) {
  if (!LEGAL_BODY_PATH.some((p) => rel.indexOf(p) !== -1)) return false
  // 精确匹配 class="..." 中的 body class (避免 legal-title vs section-title 误判).
  const m = line.match(/class="([^"]*)"/)
  if (!m) return false
  const classes = m[1].split(/\s+/)
  return LEGAL_BODY_CLASS.some((c) => classes.indexOf(c) !== -1)
}

const ALLOW_TOKENS = [
  '\u533b\u8def\u5b89', // 医路安 品牌名
  // 法律页元信息日期值常量 (legal.js): 法务同批处理, 属法律页元数据非 UI 文案.
  '2026\u5e744\u670810\u65e5', // 2026年4月10日
  // period 内部状态常量 (create-order.js:67 + wxml 逻辑比较值): 状态机常量,
  // 上屏经 summaryDate 独立 i18n 处理 (拆独立 task), wxml 逻辑比较不动.
  '\u4e0a\u5348', // 上午
  '\u4e0b\u5348', // 下午
]

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
      if (CN.test(stripped) && !isAllowed(stripped) && !isLegalBodyLine(rel, stripped)) {
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
