const { isValidPhone, isValidOTP } = require('../../utils/validate')

describe('utils/validate', () => {
  // Test 31: phone validation
  test('isValidPhone validates Chinese mobile numbers', () => {
    expect(isValidPhone('13800138000')).toBe(true)
    expect(isValidPhone('14500001111')).toBe(true)
    expect(isValidPhone('19900009999')).toBe(true)

    expect(isValidPhone('12345678901')).toBe(false) // starts with 12
    expect(isValidPhone('1380013800')).toBe(false) // 10 digits
    expect(isValidPhone('138001380001')).toBe(false) // 12 digits
    expect(isValidPhone('')).toBe(false)
    expect(isValidPhone('abc')).toBe(false)
  })

  // Test 32: OTP validation
  test('isValidOTP validates 6-digit codes', () => {
    expect(isValidOTP('123456')).toBe(true)
    expect(isValidOTP('000000')).toBe(true)

    expect(isValidOTP('12345')).toBe(false) // 5 digits
    expect(isValidOTP('1234567')).toBe(false) // 7 digits
    expect(isValidOTP('abcdef')).toBe(false)
    expect(isValidOTP('')).toBe(false)
  })
})
