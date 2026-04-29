// formatCurrency
// Action #8 — 统一金额展示为「千分位 + 两位小数」，例如 ¥1,200.00。
//
// 入参：
//   value: number | string | null | undefined
//   options?: { unit?: 'yuan' | 'cent', symbol?: string, withSymbol?: boolean }
//
// 约定：
//   - 项目内 ADR-0030：后端金额对外契约为元（number / string，例如 299.0）。
//     默认 unit='yuan'。如果传 unit='cent'，会先除以 100。
//   - null / undefined / NaN → '¥0.00'
//   - 负数 → '-¥1,200.00'（符号在 ¥ 前面，符合中文金融习惯）
//   - 大数自动千分位
//
// 示例：
//   formatCurrency(1200)          → '¥1,200.00'
//   formatCurrency(1234567.5)     → '¥1,234,567.50'
//   formatCurrency(0.1 + 0.2)     → '¥0.30'
//   formatCurrency(-50)           → '-¥50.00'
//   formatCurrency(null)          → '¥0.00'
//   formatCurrency(120000, { unit: 'cent' }) → '¥1,200.00'
//   formatCurrency(1200, { withSymbol: false }) → '1,200.00'

function formatCurrency(value, options) {
  var opts = options || {}
  var symbol = opts.symbol || '¥'
  var withSymbol = opts.withSymbol !== false
  var unit = opts.unit || 'yuan'

  var num = Number(value)
  if (value === null || value === undefined || isNaN(num)) {
    return withSymbol ? symbol + '0.00' : '0.00'
  }

  if (unit === 'cent') {
    num = num / 100
  }

  var negative = num < 0
  var abs = Math.abs(num)

  // 先固定 2 位小数，再插入千分位
  var fixed = abs.toFixed(2)
  var parts = fixed.split('.')
  var intPart = parts[0]
  var decPart = parts[1]
  var withSep = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ',')

  var body = withSep + '.' + decPart
  var prefix = (negative ? '-' : '') + (withSymbol ? symbol : '')
  return prefix + body
}

module.exports = { formatCurrency }
