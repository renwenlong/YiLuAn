/**
 * 倒计时相关工具。
 *
 * 为了方便单测、同时让页面业务代码（setInterval 内部）清晰，把"是否进入紧急态"
 * 这一阈值判断抽出来。
 */

// <30 分钟即进入紧急态
const URGENT_THRESHOLD_MS = 30 * 60 * 1000

/**
 * 剩余毫秒是否进入紧急态。
 *
 * - diffMs > 0 且 < 阈值 → true
 * - diffMs ≤ 0（已超时）或 >= 阈值 → false
 *
 * @param {number} diffMs 剩余时间（ms）
 * @param {number} [thresholdMs] 阈值（默认 30min）
 * @returns {boolean}
 */
function isCountdownUrgent(diffMs, thresholdMs) {
  var t = typeof thresholdMs === 'number' ? thresholdMs : URGENT_THRESHOLD_MS
  return diffMs > 0 && diffMs < t
}

module.exports = {
  isCountdownUrgent: isCountdownUrgent,
  URGENT_THRESHOLD_MS: URGENT_THRESHOLD_MS,
}
