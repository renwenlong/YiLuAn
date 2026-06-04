// servicePackages.js
// S2-REQ-003-P5b — 拉公开服务档位列表 + 降级兜底
//
// 端点：GET /api/v1/public/service-packages（公开访问，无 auth）
// 行为：
//   - 200 → 返 [{ code, name, price, sort_order, description }]
//   - 503/超时/任何 reject → 返 FALLBACK 三档（acceptance #4 降级兜底）
//   - 调用方应配合 UI 显示 "服务列表已降级" 提示

const { request } = require('./api')

// 硬编码三档兜底（与 utils/constants.js SERVICE_TYPES 一致；
// 当 API 不可达时使用，保证基础下单可用）
var FALLBACK_PACKAGES = [
  { code: 'full_accompany', name: '全程陪诊', price: 299, sort_order: 10, description: null, _fallback: true },
  { code: 'half_accompany', name: '半程陪诊', price: 199, sort_order: 20, description: null, _fallback: true },
  { code: 'errand', name: '代办跑腿', price: 149, sort_order: 30, description: null, _fallback: true }
]

function listPublicServicePackages() {
  return new Promise(function (resolve) {
    request({
      url: 'public/service-packages',
      method: 'GET',
      auth: false,
      timeout: 5000
    }).then(function (data) {
      if (Array.isArray(data) && data.length > 0) {
        // 归一化：API 返 price 可能 string ("299.00") 或 number (299)
        var items = data.map(function (it) {
          var p = it.price
          var num = typeof p === 'string' ? parseFloat(p) : Number(p)
          return {
            code: it.code,
            name: it.name,
            price: isFinite(num) ? num : 0,
            sort_order: typeof it.sort_order === 'number' ? it.sort_order : 0,
            description: it.description || null,
            _fallback: false
          }
        })
        // 已按 sort_order 升序（后端保证），客户端兜底再排
        items.sort(function (a, b) { return a.sort_order - b.sort_order })
        resolve(items)
      } else {
        resolve(FALLBACK_PACKAGES.slice())
      }
    }).catch(function () {
      // API 超时 / 503 / 网络错 → 降级
      resolve(FALLBACK_PACKAGES.slice())
    })
  })
}

module.exports = {
  listPublicServicePackages: listPublicServicePackages,
  FALLBACK_PACKAGES: FALLBACK_PACKAGES
}
