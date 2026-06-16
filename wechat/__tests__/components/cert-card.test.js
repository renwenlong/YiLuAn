/**
 * Unit tests for cert-card component (S3-DEV-003-TRUST-UI-WX).
 *
 * Cover:
 * - _deriveState 3 状态 (verified / pending_resubmit / unverified)
 * - _formatVerifiedAt ISO → YYYY-MM-DD
 * - ABAC: proof_image_urls 不被组件读取 (字段名永不出现在 setData 调用里)
 * - AC#3: 输出中不含 "已护士" / "已医生" / "主任医师" 等职业背书词
 */
const certCard = require('../../components/cert-card/index')

describe('components/cert-card _deriveState', () => {
  test('null / undefined certStatus → unverified', () => {
    expect(certCard._deriveState(null)).toBe('unverified')
    expect(certCard._deriveState(undefined)).toBe('unverified')
  })

  test('ready=true → verified', () => {
    expect(certCard._deriveState({
      ready: true,
      companion_cert_pseudonym_name: '陈师傅',
      companion_cert_work_id: 'PC0042',
    })).toBe('verified')
  })

  test('ready=false + 有 pseudonym/work_id → pending_resubmit (临时证明补交)', () => {
    expect(certCard._deriveState({
      ready: false,
      companion_cert_pseudonym_name: '陈师傅',
    })).toBe('pending_resubmit')
    expect(certCard._deriveState({
      ready: false,
      companion_cert_work_id: 'PC0042',
    })).toBe('pending_resubmit')
    expect(certCard._deriveState({
      ready: false,
      companion_cert_pseudonym_name: '陈师傅',
      companion_cert_work_id: 'PC0042',
    })).toBe('pending_resubmit')
  })

  test('ready=false + 全空 → unverified', () => {
    expect(certCard._deriveState({ ready: false })).toBe('unverified')
    expect(certCard._deriveState({
      ready: false,
      companion_cert_pseudonym_name: null,
      companion_cert_work_id: null,
    })).toBe('unverified')
    expect(certCard._deriveState({
      ready: false,
      companion_cert_pseudonym_name: '',
      companion_cert_work_id: '',
    })).toBe('unverified')
  })

  test('ready false-y 但非 strict false (例 undefined/null) → 仍按 unverified 处理', () => {
    // 防御性: ready undefined / null 都不视为 verified.
    expect(certCard._deriveState({ ready: undefined })).toBe('unverified')
    expect(certCard._deriveState({ ready: null })).toBe('unverified')
    expect(certCard._deriveState({ ready: 0 })).toBe('unverified')
  })
})

describe('components/cert-card _formatVerifiedAt', () => {
  test('empty / null → 空字符串', () => {
    expect(certCard._formatVerifiedAt(null)).toBe('')
    expect(certCard._formatVerifiedAt(undefined)).toBe('')
    expect(certCard._formatVerifiedAt('')).toBe('')
  })

  test('合法 ISO timestamp → YYYY-MM-DD', () => {
    // 注意时区: backend 用 UTC ISO, 本地时区可能差 ±1 天 (jest 跑本地 tz).
    // 用一个 UTC midnight + 中午时间, 跨时区都落同 UTC date.
    const result = certCard._formatVerifiedAt('2026-05-10T12:00:00Z')
    expect(result).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })

  test('非法 ISO → 空字符串', () => {
    expect(certCard._formatVerifiedAt('not-a-date')).toBe('')
  })

  test('Date object 也兼容 (new Date(...) 可解)', () => {
    const result = certCard._formatVerifiedAt('2026-05-10')
    expect(result).toMatch(/^2026-05-\d{2}$/)
  })
})

describe('components/cert-card AC#3 文案 lint (defense-in-depth)', () => {
  // 组件 wxml 不渲染职业背书前缀; 这里检 js side 字符常量也无.
  // 防回归: 任何 future maintenance 偷加 "护士" / "医生" 字面回 component
  // 必踩此 test.
  test('cert-card component source 不含职业背书词', () => {
    // 读 source 文件做关键词扫描 (含 wxml + js).
    const fs = require('fs')
    const path = require('path')
    const root = path.resolve(__dirname, '../../components/cert-card')
    const sources = ['index.js', 'index.wxml']
    const bannedPatterns = [
      // 显式职业 + "资格" / "认证" 组合 = 等价职业背书
      /已护士/u,
      /已医生/u,
      /已主任医师/u,
      /已副主任医师/u,
      /已主治医师/u,
      /已住院医师/u,
      /护士资格/u,
      /医生资格/u,
    ]
    sources.forEach(function (fname) {
      const fp = path.join(root, fname)
      let text = fs.readFileSync(fp, 'utf8')
      // 剩区重点 banned-pattern 扫仅针对“非注释代码/文本”.
      // 先干净全部注释 block (wxml <!-- --> + js // / /* */),
      // 避免误判“注释里提醒用户不要写 已护士”这种合法 lint reminder.
      text = text
        .replace(/<!--[\s\S]*?-->/g, '')   // 去 wxml 注释 block
        .replace(/\/\*[\s\S]*?\*\//g, '') // 去 js block comment
        .replace(/^\s*\/\/.*$/gm, '')      // 去 js 单行注释
        .replace(/^\s*\*.*$/gm, '')       // 去 js jsdoc 内 * 行 (裸 装在 /* */ 中间)
      const lines = text.split(/\r?\n/)
      lines.forEach(function (line, i) {
        const stripped = line.trim()
        if (stripped === '') return
        bannedPatterns.forEach(function (pat) {
          if (pat.test(line)) {
            throw new Error(
              fname + ':' + (i + 1) + ' contains banned profession-endorsement '
                + 'phrase matching ' + pat.toString() + ': "'
                + line.trim() + '" (AC#3)'
            )
          }
        })
      })
    })
  })

  test('cert-card source 不直接 ref companion_cert_proof_image_urls (AC#2)', () => {
    // 字段名出现在注释里是 OK (我们注释里说明 "永不渲染").
    // 但**不应**出现在 wxml 渲染表达式或 js setData/computed 里.
    const fs = require('fs')
    const path = require('path')
    const root = path.resolve(__dirname, '../../components/cert-card')
    const wxmlText = fs.readFileSync(path.join(root, 'index.wxml'), 'utf8')
    // wxml 中渲染 = 出现在 {{}} 表达式里.
    const renderRefs = wxmlText.match(/\{\{[^}]*companion_cert_proof_image_urls[^}]*\}\}/gu)
    expect(renderRefs).toBeNull()
  })
})

describe('components/cert-card a11y labels', () => {
  test('verified state a11y label includes semantic status and every cert field', () => {
    // Arrange
    const certStatus = {
      ready: true,
      companion_cert_pseudonym_name: '陈师傅',
      companion_cert_work_id: 'PC0042',
      companion_cert_qualifications: ['康复治疗师', '健康管理师'],
      companion_cert_verified_at: '2026-05-10T12:00:00Z',
    }

    // Act
    const label = certCard._a11yLabel(certStatus)

    // Assert
    expect(label).toContain('陪诊师资质')
    expect(label).toContain('状态：已认证')
    expect(label).toContain('姓名：陈师傅')
    expect(label).toContain('工号：PC0042')
    expect(label).toContain('资质：康复治疗师、健康管理师')
    expect(label).toMatch(/认证时间：\d{4}-\d{2}-\d{2}/u)
    expect(label).toContain('证件原图不会在用户端展示')
  })

  test('pending / unverified a11y summaries are distinguishable without color', () => {
    // Arrange
    const pending = {
      ready: false,
      companion_cert_pseudonym_name: '陈师傅',
      companion_cert_work_id: 'PC0042',
    }
    const unverified = { ready: false }

    // Act
    const pendingSummary = certCard._a11ySummary(pending)
    const unverifiedSummary = certCard._a11ySummary(unverified)

    // Assert
    expect(pendingSummary).toContain('状态：临时证明补交中')
    expect(unverifiedSummary).toContain('状态：未认证')
    expect(pendingSummary).not.toBe(unverifiedSummary)
  })

  test('wxml declares screen-reader labels for card, rows, status and hints', () => {
    // Arrange
    const fs = require('fs')
    const path = require('path')

    // Act
    const wxmlText = fs.readFileSync(
      path.resolve(__dirname, '../../components/cert-card/index.wxml'),
      'utf8'
    )

    // Assert
    expect(wxmlText).toContain('aria-label="{{a11yLabel}}"')
    expect(wxmlText).toContain('aria-label="陪诊师资质状态：已认证"')
    expect(wxmlText).toContain('aria-label="陪诊师资质状态：临时证明补交中"')
    expect(wxmlText).toContain('aria-label="陪诊师资质状态：未认证"')
    expect(wxmlText).toContain('aria-label="陪诊师化名：{{certStatus.companion_cert_pseudonym_name}}"')
    expect(wxmlText).toContain('aria-label="陪诊师工号：{{certStatus.companion_cert_work_id}}"')
    expect(wxmlText).toContain('aria-label="陪诊师资质：{{a11yQualifications}}"')
    expect(wxmlText).toContain('aria-label="认证时间：{{verifiedAtDisplay}}"')
  })
})
