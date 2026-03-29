const ENV = {
  development: {
    API_BASE_URL: 'http://localhost:8000/api/v1',
    WS_BASE_URL: 'ws://localhost:8000',
  },
  production: {
    API_BASE_URL: 'https://api.yiluan.app/api/v1',
    WS_BASE_URL: 'wss://api.yiluan.app',
  },
}

// __wxConfig.envVersion: 'develop' | 'trial' | 'release'
const env = typeof __wxConfig !== 'undefined' && __wxConfig.envVersion === 'release'
  ? 'production'
  : 'development'

module.exports = {
  ...ENV[env],
  OTP_LENGTH: 6,
  DEV_OTP: '000000',
  PAGE_SIZE: 20,
}
