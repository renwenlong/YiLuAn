/**
 * Contract service — S3-DEV-001-CONTRACT-UI (ADR-0047 §6.2 + §6.3)
 *
 * 对应后端 PR #206 endpoint:
 * - POST /api/v1/contracts/{id}/accept  (用户勾选合同同意, 写 user_audit_logs)
 * - GET  /api/v1/contracts/{id}         (查看合同 + signed URL TTL=15min)
 *
 * 不暴露 admin invalidate (该端点 admin H5 走, 微信端不调).
 *
 * 注意: 必须 PR #207 OrderResponse 已含 contract_id 才能用 (前端调本服务
 * 前必须先从 order detail 拿到 contract_id, null 视为合同未生成).
 */

const { request } = require('./api')

/**
 * 用户勾选 "我已阅读" → 写 audit log.
 *
 * 失败不阻断支付按钮 (UI 层 disabled 解锁由 checkbox state 控制,
 * audit log 失败由后端 cron 兜底重试; 前端只展示 toast 不弹 modal).
 *
 * @param {string} contractId UUID
 * @returns {Promise<{contract_id, order_id, accepted_at, audit_log_id}>}
 */
function acceptContract(contractId) {
  return request({
    url: 'contracts/' + contractId + '/accept',
    method: 'POST',
    data: {},
  })
}

/**
 * 查看合同详情 + 取 signed URL (15min TTL).
 *
 * status != 'active' 时 signed_url=null, 前端按 status 显示对应文案:
 * - pending_generation / generating: "合同生成中, 稍后查看"
 * - generation_failed / generation_permanently_failed: "合同生成失败, 客服已介入"
 * - manually_invalidated: "合同已作废, 联系客服"
 *
 * 服务端会写 user_audit_logs.contract_viewed (PIPL 取证).
 *
 * @param {string} contractId UUID
 * @returns {Promise<{contract_id, order_id, template_version, status,
 *                    signed_url, signed_url_expires_at, generated_at}>}
 */
function getContract(contractId) {
  return request({
    url: 'contracts/' + contractId,
    method: 'GET',
  })
}

module.exports = { acceptContract, getContract }
