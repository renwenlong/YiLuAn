const ENV = {
  staging: {
    // 微信开发者工具 / trial 默认走本机 staging docker 栈（ADR-0030）：
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
// WeChat's enum is fixed; app runtime maps non-release builds to staging.
const envVersion = typeof __wxConfig !== 'undefined' ? __wxConfig.envVersion : 'trial'
const env = envVersion === 'release' ? 'production' : 'staging'

module.exports = {
  ...ENV[env],
  OTP_LENGTH: 6,
  PAGE_SIZE: 20,
}
