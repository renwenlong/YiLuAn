const ENV = {
  development: {
    // Dev/联调走 staging docker 栈（ADR-0030）：
    //   - nginx-staging 暴露 127.0.0.1:18080，后端 + PG + Redis + mocks 全在 docker network 内
    //   - 微信开发者工具：详情 → 本地设置 → 勾选『不校验合法域名/web-view(业务域名)/TLS 版本以及 HTTPS 证书』
    API_BASE_URL: 'http://localhost:18080/api/v1',
    WS_BASE_URL: 'ws://localhost:18080',
  },
  production: {
    API_BASE_URL: 'https://api.yiluan.app/api/v1',
    WS_BASE_URL: 'wss://api.yiluan.app',
  },
}

// __wxConfig.envVersion: 'develop' | 'trial' | 'release'
const envVersion = typeof __wxConfig !== 'undefined' ? __wxConfig.envVersion : 'develop'
const env = envVersion === 'release' ? 'production' : 'development'

module.exports = {
  ...ENV[env],
  OTP_LENGTH: 6,
  DEV_OTP: env === 'development' ? '000000' : null,
  PAGE_SIZE: 20,
}
