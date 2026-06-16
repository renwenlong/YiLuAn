describe('config/index.js staging defaults', () => {
  const originalEnvVersion = global.__wxConfig.envVersion

  afterEach(() => {
    global.__wxConfig.envVersion = originalEnvVersion
    jest.resetModules()
  })

  test('develop build maps to staging backend', () => {
    global.__wxConfig.envVersion = 'develop'
    jest.resetModules()
    const config = require('../../config/index')
    expect(config.API_BASE_URL).toBe('http://localhost:18080/api/v1')
    expect(config.WS_BASE_URL).toBe('ws://localhost:18080')
  })

  test('trial build maps to staging backend', () => {
    global.__wxConfig.envVersion = 'trial'
    jest.resetModules()
    const config = require('../../config/index')
    expect(config.API_BASE_URL).toBe('http://localhost:18080/api/v1')
    expect(config.WS_BASE_URL).toBe('ws://localhost:18080')
  })

  test('release build maps to production backend', () => {
    global.__wxConfig.envVersion = 'release'
    jest.resetModules()
    const config = require('../../config/index')
    expect(config.API_BASE_URL).toBe('https://api.yiluan.app/api/v1')
    expect(config.WS_BASE_URL).toBe('wss://api.yiluan.app')
  })
})
