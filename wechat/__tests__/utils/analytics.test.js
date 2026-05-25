const analytics = require('../../utils/analytics')

describe('utils/analytics', () => {
  beforeEach(() => {
    analytics._resetForTests()
    global.getCurrentPages = () => [{ route: 'pages/test/index' }]
  })

  afterEach(() => {
    analytics._resetForTests()
    delete global.getCurrentPages
  })

  test('FUNNEL_STEPS 暴露 5 个核心节点', () => {
    expect(Object.keys(analytics.FUNNEL_STEPS).sort()).toEqual([
      'COMPANION_DETAIL_VIEW',
      'COMPANION_LIST_VIEW',
      'ORDER_CREATE_START',
      'ORDER_SUBMIT',
      'PAYMENT_SUCCESS',
    ])
    // 命名空间统一 funnel.<step>
    Object.values(analytics.FUNNEL_STEPS).forEach((v) => {
      expect(v).toMatch(/^funnel\./)
    })
  })

  test('trackFunnel 没 emitter 时静默丢弃，不抛错', () => {
    expect(() => {
      analytics.trackFunnel(analytics.FUNNEL_STEPS.ORDER_SUBMIT, { order_id: 'o1' })
    }).not.toThrow()
  })

  test('trackFunnel 走 emitter 并带 page / env 元数据', () => {
    const events = []
    analytics.setEmitter((ev) => events.push(ev))
    analytics.setClientMeta({ env: 'prod', sdk: '1.0' })
    analytics.trackFunnel(analytics.FUNNEL_STEPS.ORDER_SUBMIT, {
      order_id: 'o-1', service_type: 'diagnosis', amount_cents: 19900,
    })
    expect(events.length).toBe(1)
    expect(events[0].event_type).toBe('funnel.order_submit')
    expect(events[0].payload).toEqual({
      order_id: 'o-1', service_type: 'diagnosis', amount_cents: 19900,
    })
    expect(events[0].client_meta).toMatchObject({
      page: 'pages/test/index', env: 'prod', sdk: '1.0',
    })
    expect(typeof events[0].ts).toBe('number')
  })

  test('trackFunnel 拒绝白名单外的 step（防止手拼错字符串）', () => {
    const events = []
    analytics.setEmitter((ev) => events.push(ev))
    analytics.trackFunnel('funnel.bogus_step', { x: 1 })
    analytics.trackFunnel('not_a_funnel', { x: 1 })
    expect(events.length).toBe(0)
  })

  test('payload 白名单外的 key 被静默剥掉', () => {
    const events = []
    analytics.setEmitter((ev) => events.push(ev))
    analytics.trackFunnel(analytics.FUNNEL_STEPS.ORDER_SUBMIT, {
      order_id: 'o1',
      phone: '13800138000',        // 不在白名单
      real_name: '张三',            // 不在白名单
      arbitrary: 'x',               // 不在白名单
    })
    expect(events.length).toBe(1)
    expect(events[0].payload).toEqual({ order_id: 'o1' })
    expect(events[0].payload).not.toHaveProperty('phone')
    expect(events[0].payload).not.toHaveProperty('real_name')
  })

  test('payload string 中夹带手机号 / 身份证会被 mask', () => {
    const events = []
    analytics.setEmitter((ev) => events.push(ev))
    analytics.trackFunnel(analytics.FUNNEL_STEPS.ORDER_SUBMIT, {
      source: 'user 13800138000 referred',
    })
    expect(events[0].payload.source).toBe('user 1********** referred')
  })

  test('同 step 5 秒内限流（avoids onShow 反复触发）', () => {
    const events = []
    analytics.setEmitter((ev) => events.push(ev))
    analytics.trackFunnel(analytics.FUNNEL_STEPS.COMPANION_LIST_VIEW)
    analytics.trackFunnel(analytics.FUNNEL_STEPS.COMPANION_LIST_VIEW)
    analytics.trackFunnel(analytics.FUNNEL_STEPS.COMPANION_LIST_VIEW)
    expect(events.length).toBe(1)
    // 不同 step 不互相限流
    analytics.trackFunnel(analytics.FUNNEL_STEPS.ORDER_SUBMIT)
    expect(events.length).toBe(2)
  })

  test('emitter 抛错被吞掉，业务不感知', () => {
    analytics.setEmitter(() => { throw new Error('reporter down') })
    expect(() => {
      analytics.trackFunnel(analytics.FUNNEL_STEPS.PAYMENT_SUCCESS)
    }).not.toThrow()
  })

  test('track 通用埋点 — 不限制 event_type 但走同样的 emitter', () => {
    const events = []
    analytics.setEmitter((ev) => events.push(ev))
    analytics.track('custom.ab_assignment', { source: 'home' })
    expect(events.length).toBe(1)
    expect(events[0].event_type).toBe('custom.ab_assignment')
  })

  test('setEmitter(null) 关闭上报（紧急止血）', () => {
    const events = []
    analytics.setEmitter((ev) => events.push(ev))
    analytics.trackFunnel(analytics.FUNNEL_STEPS.ORDER_SUBMIT)
    analytics.setEmitter(null)
    analytics.trackFunnel(analytics.FUNNEL_STEPS.PAYMENT_SUCCESS)
    expect(events.length).toBe(1)
  })
})
