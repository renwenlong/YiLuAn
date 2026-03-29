const {
  getAccessToken,
  setAccessToken,
  getRefreshToken,
  setRefreshToken,
  clearTokens,
  isTokenExpired,
} = require('../../utils/token')

beforeEach(() => {
  __resetWxStorage()
})

// Helper: create a fake JWT with given payload
function fakeJWT(payload) {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
  const body = btoa(JSON.stringify(payload))
  return header + '.' + body + '.signature'
}

// Polyfill btoa for Node.js test env
function btoa(str) {
  return Buffer.from(str, 'utf-8').toString('base64')
}

describe('utils/token', () => {
  // Test 24: get token
  test('getAccessToken returns stored token', () => {
    wx.setStorageSync('yiluan_access_token', 'abc123')
    expect(getAccessToken()).toBe('abc123')
  })

  // Test 25: set token
  test('setAccessToken stores token', () => {
    setAccessToken('my_token')
    expect(wx.getStorageSync('yiluan_access_token')).toBe('my_token')
  })

  // Test 26: clear tokens
  test('clearTokens removes both tokens', () => {
    setAccessToken('at')
    setRefreshToken('rt')
    clearTokens()
    expect(getAccessToken()).toBeNull()
    expect(getRefreshToken()).toBeNull()
  })

  // Test 27: isTokenExpired
  test('isTokenExpired returns true for expired token', () => {
    // Expired 1 hour ago
    const expiredToken = fakeJWT({ exp: Math.floor(Date.now() / 1000) - 3600, sub: 'u1' })
    expect(isTokenExpired(expiredToken)).toBe(true)

    // Expires 1 hour from now
    const validToken = fakeJWT({ exp: Math.floor(Date.now() / 1000) + 3600, sub: 'u1' })
    expect(isTokenExpired(validToken)).toBe(false)

    // No token
    expect(isTokenExpired(null)).toBe(true)
    expect(isTokenExpired('')).toBe(true)
  })
})
