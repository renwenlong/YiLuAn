#!/usr/bin/env node
// Bundle size dashboard for the WeChat mini program.
//
// What it does: walks the shippable source tree (everything that gets
// uploaded to WeChat — excludes node_modules, __tests__, tsconfig, docs)
// and reports total bytes + per-top-level-directory breakdown.
//
// Why: WeChat has a hard 2 MB main-package limit and 20 MB total across
// sub-packages. We want a CI signal before we accidentally cross either.
//
// Output:
//   - human-readable summary to stdout
//   - JSON report at wechat/bundle-size.json (CI uploads as artifact)
//   - exit 1 if total exceeds soft cap (configurable via env)
//
// Baseline comparison: pass --baseline=path/to/old.json to diff and warn
// if growth exceeds +10%.

const fs = require('fs')
const path = require('path')

const ROOT = path.resolve(__dirname, '..')
const REPORT_PATH = path.join(ROOT, 'bundle-size.json')

// Soft warning cap (bytes). Hard limit on WeChat is 2 MB for main pkg,
// but our source tree is what we measure (uploaded raw). 4 MB is generous
// headroom for a typical project of this size.
const SOFT_CAP_BYTES = parseInt(process.env.BUNDLE_SOFT_CAP || (4 * 1024 * 1024), 10)
// Growth threshold vs baseline (fraction).
const GROWTH_THRESHOLD = 0.10

// Directories/files to skip — these are dev-only, not uploaded.
const SKIP_DIRS = new Set([
  'node_modules', '__tests__', '.git', 'coverage',
  'docs', 'e2e', 'scripts',
])
const SKIP_EXTS = new Set(['.md', '.test.js', '.snap'])
const SKIP_FILES = new Set([
  'package.json', 'package-lock.json', 'jest.config.js',
  'tsconfig.json', 'bundle-size.json',
])

function shouldSkip(relPath, name, isDir) {
  if (isDir) return SKIP_DIRS.has(name)
  if (SKIP_FILES.has(name)) return true
  if (name.endsWith('.test.js')) return true
  const ext = path.extname(name)
  if (SKIP_EXTS.has(ext)) return true
  return false
}

function walk(dir, relBase) {
  let total = 0
  let fileCount = 0
  const entries = fs.readdirSync(dir, { withFileTypes: true })
  for (const ent of entries) {
    const rel = relBase ? path.join(relBase, ent.name) : ent.name
    if (shouldSkip(rel, ent.name, ent.isDirectory())) continue
    const full = path.join(dir, ent.name)
    if (ent.isDirectory()) {
      const sub = walk(full, rel)
      total += sub.total
      fileCount += sub.fileCount
    } else if (ent.isFile()) {
      total += fs.statSync(full).size
      fileCount += 1
    }
  }
  return { total: total, fileCount: fileCount }
}

function fmtBytes(n) {
  if (n < 1024) return n + ' B'
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB'
  return (n / 1024 / 1024).toFixed(2) + ' MB'
}

function loadBaseline(argv) {
  const flag = argv.find(function (a) { return a.indexOf('--baseline=') === 0 })
  if (!flag) return null
  const p = flag.slice('--baseline='.length)
  try {
    return JSON.parse(fs.readFileSync(p, 'utf8'))
  } catch (e) {
    console.warn('[bundle-size] failed to load baseline:', e.message)
    return null
  }
}

function main() {
  const tops = ['app.js', 'app.json', 'app.wxss', 'sitemap.json',
    'pages', 'components', 'services', 'utils', 'store', 'core',
    'config', 'styles', 'submission', 'types']
  const breakdown = {}
  let grandTotal = 0
  let grandFiles = 0

  for (const top of tops) {
    const full = path.join(ROOT, top)
    if (!fs.existsSync(full)) continue
    const stat = fs.statSync(full)
    let result
    if (stat.isDirectory()) {
      result = walk(full, top)
    } else {
      result = { total: stat.size, fileCount: 1 }
    }
    breakdown[top] = result
    grandTotal += result.total
    grandFiles += result.fileCount
  }

  const report = {
    generatedAt: new Date().toISOString(),
    totalBytes: grandTotal,
    totalFiles: grandFiles,
    softCapBytes: SOFT_CAP_BYTES,
    breakdown: breakdown,
  }

  fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2))

  // Human output
  console.log('=== WeChat Mini Program Bundle Size ===')
  console.log('Total: ' + fmtBytes(grandTotal) + ' (' + grandFiles + ' files)')
  console.log('Soft cap: ' + fmtBytes(SOFT_CAP_BYTES))
  console.log('')
  console.log('Breakdown:')
  const rows = Object.keys(breakdown).map(function (k) {
    return { name: k, total: breakdown[k].total, files: breakdown[k].fileCount }
  }).sort(function (a, b) { return b.total - a.total })
  for (const row of rows) {
    const pct = ((row.total / grandTotal) * 100).toFixed(1)
    console.log('  ' + row.name.padEnd(14) + fmtBytes(row.total).padStart(10) +
      '  (' + pct + '%, ' + row.files + ' files)')
  }
  console.log('')

  // Baseline compare
  const baseline = loadBaseline(process.argv)
  let exitCode = 0
  if (baseline && baseline.totalBytes) {
    const delta = grandTotal - baseline.totalBytes
    const pct = delta / baseline.totalBytes
    const sign = delta >= 0 ? '+' : ''
    console.log('Baseline: ' + fmtBytes(baseline.totalBytes))
    console.log('Delta:    ' + sign + fmtBytes(Math.abs(delta)) +
      ' (' + sign + (pct * 100).toFixed(2) + '%)')
    if (pct > GROWTH_THRESHOLD) {
      console.log('::warning::Bundle grew by ' + (pct * 100).toFixed(1) +
        '% vs baseline (threshold: ' + (GROWTH_THRESHOLD * 100) + '%)')
    }
  }

  if (grandTotal > SOFT_CAP_BYTES) {
    console.log('::warning::Bundle size ' + fmtBytes(grandTotal) +
      ' exceeds soft cap ' + fmtBytes(SOFT_CAP_BYTES))
    exitCode = process.env.BUNDLE_FAIL_ON_CAP === '1' ? 1 : 0
  }

  process.exit(exitCode)
}

main()
