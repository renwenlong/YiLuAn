#!/usr/bin/env node
/**
 * Vite dev proxy ↔ nginx prod 反代路径一致性 gate
 * (S2-DEV-013 acceptance #8, 胡桃 ADR-0042 review §5.1 第 1 项)
 *
 * 思路：读 vite.config.ts 的 server.proxy keys + nginx 配置（如有）的
 * location 路径前缀，diff 必须一致。
 *
 * Phase 1 实施：vite.config.ts 已配 /api/v1 proxy；nginx 配 PR-C 加，
 * 本 gate 当前只校验 vite proxy 命中 /api/v1 + base path 与 basename 一致。
 *
 * Phase 2 升级：解析 deploy/nginx/nginx.conf 真实 location，确保完全 align。
 */
import { readFileSync } from 'node:fs'

const viteRaw = readFileSync('vite.config.ts', 'utf-8')
const mainRaw = readFileSync('src/main.tsx', 'utf-8')

const errors = []

// 1. vite.config.ts proxy 必须含 /api/v1
if (!/\/api\/v1.*target.*http/s.test(viteRaw)) {
  errors.push("vite.config.ts: 缺 /api/v1 proxy 配置")
}

// 2. base path = '/admin-v2/' 与 main.tsx basename 一致
const viteBase = viteRaw.match(/base:\s*['"]([^'"]+)['"]/)?.[1]
const mainBase = mainRaw.match(/basename=['"]([^'"]+)['"]/)?.[1]
if (!viteBase || !mainBase) {
  errors.push(`base/basename 不齐: vite=${viteBase}, main=${mainBase}`)
} else if (viteBase.replace(/\/$/, '') !== mainBase.replace(/\/$/, '')) {
  errors.push(
    `vite base "${viteBase}" 与 main.tsx basename "${mainBase}" 不一致`,
  )
}

// 3. apiClient baseURL = '/api/v1'（不能写 absolute URL）
const clientRaw = readFileSync('src/shared/api/client.ts', 'utf-8')
if (!/baseURL:\s*['"]\/api\/v1['"]/.test(clientRaw)) {
  errors.push("api/client.ts baseURL 不是相对 '/api/v1'，dev/prod 路径会漂移")
}

if (errors.length) {
  console.error('❌ admin-v2 API path consistency check failed:')
  for (const e of errors) console.error(`  - ${e}`)
  process.exit(1)
}
console.log('✅ admin-v2 API path consistency check passed')
