module.exports = {
  testEnvironment: 'node',
  // watchman 二进制本机未装 (which watchman 空)，但 jest 默认 watchman:true →
  // 冷启动偶发 stall 隐患 (解释了 jest hang 时好时坏/事后复现不出)。
  // 关掉零依赖硬化，实测 --watchman=false --runInBand 525 tests exit 0 无害。
  watchman: false,
  setupFiles: ['./__tests__/setup.js'],
  testMatch: ['**/__tests__/**/*.test.js'],
  collectCoverageFrom: [
    'services/**/*.js',
    'store/**/*.js',
    'utils/**/*.js',
  ],
}
