const { formatPrice, formatDate, formatPhone, formatOrderStatus } = require('../../utils/format')

describe('utils/format', () => {
  // Test 28: formatPrice
  test('formatPrice formats numbers with ¥ and 2 decimals', () => {
    expect(formatPrice(299)).toBe('¥299.00')
    expect(formatPrice(0)).toBe('¥0.00')
    expect(formatPrice(1.5)).toBe('¥1.50')
    expect(formatPrice('abc')).toBe('¥0.00')
    expect(formatPrice(null)).toBe('¥0.00')
  })

  // Test 29: formatDate
  test('formatDate formats ISO string to YYYY-MM-DD HH:mm', () => {
    const d = new Date(2026, 2, 15, 9, 5) // March 15, 2026 09:05
    const result = formatDate(d.toISOString())
    expect(result).toBe('2026-03-15 09:05')

    expect(formatDate(null)).toBe('')
    expect(formatDate('')).toBe('')
  })

  // Test 29b: formatPhone
  test('formatPhone masks middle digits', () => {
    expect(formatPhone('13800138000')).toBe('138****8000')
    expect(formatPhone('123')).toBe('123')
    expect(formatPhone(null)).toBe('')
  })

  // Test 30: formatOrderStatus
  test('formatOrderStatus returns Chinese label', () => {
    expect(formatOrderStatus('created')).toBe('待接单')
    expect(formatOrderStatus('completed')).toBe('已完成')
    expect(formatOrderStatus('unknown_status')).toBe('unknown_status')
    expect(formatOrderStatus(null)).toBe('')
  })
})
