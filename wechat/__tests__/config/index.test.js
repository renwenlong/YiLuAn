describe('config/index.js DEV_OTP env isolation', () => {
  const originalEnvVersion = global.__wxConfig.envVersion

  afterEach(() => {
    global.__wxConfig.envVersion = originalEnvVersion
    jest.resetModules()
  })

  test('DEV_OTP is "000000" in develop environment', () => {
    global.__wxConfig.envVersion = 'develop'
    jest.resetModules()
    const config = require('../../config/index')
    expect(config.DEV_OTP).toBe('000000')
  })

  test('DEV_OTP is "000000" in trial environment', () => {
    global.__wxConfig.envVersion = 'trial'
    jest.resetModules()
    const config = require('../../config/index')
    expect(config.DEV_OTP).toBe('000000')
  })

  test('DEV_OTP is null in release (production) environment', () => {
    global.__wxConfig.envVersion = 'release'
    jest.resetModules()
    const config = require('../../config/index')
    expect(config.DEV_OTP).toBeNull()
  })

  test('login flow must not bypass OTP verification when DEV_OTP is null', () => {
    global.__wxConfig.envVersion = 'release'
    jest.resetModules()
    const config = require('../../config/index')
    const userInputCode = '000000'
    const shouldBypass = config.DEV_OTP && userInputCode === config.DEV_OTP
    expect(shouldBypass).toBeFalsy()
  })
})
