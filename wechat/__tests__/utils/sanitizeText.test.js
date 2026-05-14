const { sanitizeText, DEFAULT_MAX_LEN } = require('../../utils/sanitizeText')

describe('utils/sanitizeText', () => {
  test('returns empty string for null/undefined', () => {
    expect(sanitizeText(null)).toBe('')
    expect(sanitizeText(undefined)).toBe('')
  })

  test('coerces non-string input', () => {
    expect(sanitizeText(123)).toBe('123')
    expect(sanitizeText({ a: 1 })).toBe('[object Object]')
  })

  test('strips ASCII control characters but keeps \\n \\t \\r', () => {
    const dirty = 'hi\x00\x01\x02 there\x07!'
    expect(sanitizeText(dirty)).toBe('hi there!')

    const withSpacing = 'a\nb\tc\rd'
    expect(sanitizeText(withSpacing)).toBe('a\nb\tc\rd')
  })

  test('collapses 3+ consecutive newlines to 2', () => {
    const input = 'top\n\n\n\n\nbottom'
    expect(sanitizeText(input)).toBe('top\n\nbottom')
  })

  test('truncates to default 200 chars + ellipsis', () => {
    const long = 'x'.repeat(300)
    const out = sanitizeText(long)
    expect(out.length).toBe(DEFAULT_MAX_LEN + 2) // 200 + '……'
    expect(out.endsWith('……')).toBe(true)
  })

  test('honours maxLen override', () => {
    const out = sanitizeText('abcdefghij', { maxLen: 5 })
    expect(out).toBe('abcde……')
  })

  test('does not truncate when within limit', () => {
    expect(sanitizeText('hello', { maxLen: 200 })).toBe('hello')
  })

  test('phishing-style payload is truncated and stripped', () => {
    // Realistic abuse: long payload with control bytes pretending to be
    // multi-line "support contact" instructions.
    const evil =
      '您的账户已冻结，请添加客服微信 ' +
      '\x00\x01wx_support_official_2026' +
      '\n\n\n\n\n\n\n以避免资金损失。' +
      ' '.repeat(500)
    const out = sanitizeText(evil)
    expect(out.length).toBeLessThanOrEqual(DEFAULT_MAX_LEN + 2)
    expect(out).not.toMatch(/\x00/)
    expect(out).not.toMatch(/\n{3,}/)
  })
})
