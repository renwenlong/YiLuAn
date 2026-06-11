/**
 * services/precheck.js — S3-DEV-003-TRUST-UI-WX HTTP API.
 *
 * 患者订单付款前看的 4 信任卡 (合同 / 保险 / AI 准备包 / 陪诊师资质)
 * precheck 状态. 本 task 微信端仅消费 companion_cert_status 子对象 +
 * 4 个 cert 字段 (cert_status / cert_pseudonym_name / cert_work_id /
 * cert_verified_at).
 *
 * 字段契约: backend/app/schemas/order_precheck.py::OrderPrecheckSummaryView
 * (ABAC Layer 1 positive-list, negative-list 17 字段后端永不返回).
 *
 * 跨端契约对齐 ios/YiLuAn/Features/Precheck/Models/OrderPrecheckSummary.swift.
 */
const { request } = require('./api')

/**
 * GET /api/v1/users/orders/{order_id}/precheck-status
 *
 * Cache hit P95 ≤200ms / miss ≤800ms (backend SLO).
 * ABAC: patient role only; 跨订单 404 (hybrid mask).
 *
 * 返回 schema (本 task 关注字段):
 *   - companion_cert_status: { ready, companion_cert_pseudonym_name,
 *     companion_cert_work_id, companion_cert_qualifications,
 *     companion_cert_proof_image_urls, companion_cert_verified_at }
 *
 * **注意**: companion_cert_proof_image_urls 是 signed URL TTL ≤15min,
 *           本 task AC#2 要求 **不渲染原图**, 微信端拿到但不显示.
 */
function getOrderPrecheckStatus(orderId) {
  return request({
    url: 'users/orders/' + orderId + '/precheck-status',
    method: 'GET',
  })
}

module.exports = {
  getOrderPrecheckStatus: getOrderPrecheckStatus,
}
