const { formatCurrency } = require('../../utils/formatCurrency')

describe('utils/formatCurrency (Action #8 — 千分位 + 两位小数)', () => {
  test('整数：基础千分位', () => {
    expect(formatCurrency(1200)).toBe('¥1,200.00')
    expect(formatCurrency(0)).toBe('¥0.00')
    expect(formatCurrency(299)).toBe('¥299.00')
  })

  test('小数：补齐两位 / 截断到两位', () => {
    expect(formatCurrency(1.5)).toBe('¥1.50')
    expect(formatCurrency(0.1 + 0.2)).toBe('¥0.30') // 浮点精度
    expect(formatCurrency('1234.5')).toBe('¥1,234.50')
  })

  test('大数：多组千分位', () => {
    expect(formatCurrency(1234567)).toBe('¥1,234,567.00')
    expect(formatCurrency(1234567890.99)).toBe('¥1,234,567,890.99')
  })

  test('负数：- 在 ¥ 前', () => {
    expect(formatCurrency(-50)).toBe('-¥50.00')
    expect(formatCurrency(-1234.5)).toBe('-¥1,234.50')
  })

  test('null / undefined / NaN / 非法 → ¥0.00', () => {
    expect(formatCurrency(null)).toBe('¥0.00')
    expect(formatCurrency(undefined)).toBe('¥0.00')
    expect(formatCurrency(NaN)).toBe('¥0.00')
    expect(formatCurrency('abc')).toBe('¥0.00')
  })

  test('字符串数字也支持', () => {
    expect(formatCurrency('1200')).toBe('¥1,200.00')
    expect(formatCurrency('1200.5')).toBe('¥1,200.50')
  })

  test('unit=cent：先除以 100', () => {
    expect(formatCurrency(120000, { unit: 'cent' })).toBe('¥1,200.00')
    expect(formatCurrency(99, { unit: 'cent' })).toBe('¥0.99')
    expect(formatCurrency(0, { unit: 'cent' })).toBe('¥0.00')
  })

  test('options.symbol 自定义币符', () => {
    expect(formatCurrency(1200, { symbol: 'CNY ' })).toBe('CNY 1,200.00')
    expect(formatCurrency(-50, { symbol: 'CNY ' })).toBe('-CNY 50.00')
  })

  test('options.withSymbol=false 仅返回纯数字串', () => {
    expect(formatCurrency(1200, { withSymbol: false })).toBe('1,200.00')
    expect(formatCurrency(null, { withSymbol: false })).toBe('0.00')
    expect(formatCurrency(-1200, { withSymbol: false })).toBe('-1,200.00')
  })
})
