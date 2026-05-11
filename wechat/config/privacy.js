/**
 * 历史兼容 shim — 权威源已迁移至 pages/legal/config/legal.js。
 * 原为主包 services/utils 零散存放，[code-quality] 提示“分包独享
 * 代码应下沉到分包”后下沉。这个 shim 仍是主包文件，只是 re-export，
 * 体积志可忽。如果以后所有调用方都迁到 pages/legal/config/legal，可删。
 */
module.exports = require('../pages/legal/config/legal')
