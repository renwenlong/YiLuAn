/**
 * Tests for utils/countdown.isCountdownUrgent
 * 覆盖：紧急阈值（<30min）切换边界
 */

const { isCountdownUrgent, URGENT_THRESHOLD_MS } = require('../../utils/countdown')

describe('utils/countdown.isCountdownUrgent', () => {
  test('剩余 >= 30 分钟不进入紧急态', () => {
    expect(isCountdownUrgent(30 * 60 * 1000)).toBe(false)
    expect(isCountdownUrgent(60 * 60 * 1000)).toBe(false)
    expect(isCountdownUrgent(URGENT_THRESHOLD_MS)).toBe(false)
  })

  test('剩余 < 30 分钟且 > 0 进入紧急态', () => {
    expect(isCountdownUrgent(29 * 60 * 1000)).toBe(true)
    expect(isCountdownUrgent(60 * 1000)).toBe(true)
    expect(isCountdownUrgent(URGENT_THRESHOLD_MS - 1)).toBe(true)
  })

  test('已超时（<=0）不进入紧急态（已超时另有文案）', () => {
    expect(isCountdownUrgent(0)).toBe(false)
    expect(isCountdownUrgent(-1000)).toBe(false)
  })

  test('可自定义阈值', () => {
    expect(isCountdownUrgent(5 * 60 * 1000, 10 * 60 * 1000)).toBe(true)
    expect(isCountdownUrgent(15 * 60 * 1000, 10 * 60 * 1000)).toBe(false)
  })
})
