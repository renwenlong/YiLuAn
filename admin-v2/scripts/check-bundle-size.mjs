#!/usr/bin/env node
/**
 * admin-v2 bundle size budget gate (S2-DEV-013 acceptance #10)
 *
 * 胡桃 ADR-0042 review §5.1 第 4 项：AntD Pro 5.x CSS-in-JS dist gzip < 2MB
 * CI 跑 `npm run build` 后调用本脚本，检查 dist/**.js + .css gzip 总和。
 */
import { readdirSync, statSync, readFileSync } from 'node:fs'
import { gzipSync } from 'node:zlib'
import { join } from 'node:path'

const BUDGET_BYTES = 2 * 1024 * 1024  // 2 MB gzip
const DIST_DIR = 'dist'

function walk(dir) {
  const out = []
  for (const f of readdirSync(dir)) {
    const p = join(dir, f)
    const st = statSync(p)
    if (st.isDirectory()) {
      out.push(...walk(p))
    } else if (/\.(js|css)$/.test(f)) {
      out.push(p)
    }
  }
  return out
}

const files = walk(DIST_DIR)
let total = 0
const rows = []
for (const f of files) {
  const raw = readFileSync(f)
  const gz = gzipSync(raw).length
  total += gz
  rows.push({ path: f, gz })
}

rows.sort((a, b) => b.gz - a.gz)
console.log('--- admin-v2 dist gzip size budget ---')
for (const r of rows) {
  console.log(`${(r.gz / 1024).toFixed(1)} KB gz   ${r.path}`)
}
console.log('---')
console.log(`TOTAL: ${(total / 1024 / 1024).toFixed(3)} MB gz`)
console.log(`BUDGET: ${(BUDGET_BYTES / 1024 / 1024).toFixed(1)} MB gz`)

if (total > BUDGET_BYTES) {
  console.error(
    `❌ admin-v2 dist gzip ${(total / 1024 / 1024).toFixed(3)} MB > ${(BUDGET_BYTES / 1024 / 1024).toFixed(1)} MB budget`,
  )
  process.exit(1)
}
console.log('✅ within budget')
