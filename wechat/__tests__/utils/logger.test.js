const logger = require('../../utils/logger')

describe('utils/logger', () => {
  let originalConsole
  let consoleCalls

  beforeEach(() => {
    logger._resetForTests()
    consoleCalls = []
    originalConsole = {
      debug: console.debug, info: console.info, warn: console.warn, error: console.error, log: console.log,
    }
    ;['debug', 'info', 'warn', 'error', 'log'].forEach((level) => {
      console[level] = (...args) => consoleCalls.push([level, args])
    })
    global.getCurrentPages = () => [{ route: 'pages/test/index' }]
  })

  afterEach(() => {
    Object.assign(console, originalConsole)
    delete global.getCurrentPages
    logger._resetForTests()
  })

  test('info/warn/error 同步输出到 console', () => {
    logger.info('hello', { a: 1 })
    logger.warn('careful')
    logger.error('boom')
    expect(consoleCalls.map((c) => c[0])).toEqual(['info', 'warn', 'error'])
    expect(consoleCalls[0][1][1]).toBe('hello')
    expect(consoleCalls[0][1][2]).toMatchObject({ a: 1, page: 'pages/test/index', env: 'dev' })
  })

  test('debug 默认被过滤（minLevel=info）', () => {
    logger.debug('skip me')
    expect(consoleCalls).toEqual([])
  })

  test('setMinLevel 控制门槛', () => {
    logger.setMinLevel('warn')
    logger.info('skipped')
    logger.warn('kept')
    expect(consoleCalls.map((c) => c[0])).toEqual(['warn'])
  })

  test('reporter 仅 warn/error 触发，info 不触发', () => {
    const reported = []
    logger.setReporter((ev) => reported.push(ev))
    logger.info('skipped')
    logger.warn('captured', { code: 'NET' })
    logger.error('boom')
    expect(reported.length).toBe(2)
    expect(reported[0].level).toBe('warn')
    expect(reported[0].message).toBe('captured')
    expect(reported[0].context).toMatchObject({ code: 'NET', env: 'dev' })
    expect(reported[1].level).toBe('error')
  })

  test('reporter=null 关闭上报（紧急止血）', () => {
    const reported = []
    logger.setReporter((ev) => reported.push(ev))
    logger.warn('w1')
    logger.setReporter(null)
    logger.warn('w2')
    expect(reported.length).toBe(1)
  })

  test('上报失败被吞掉（绝不二次抛）', () => {
    logger.setReporter(() => { throw new Error('reporter down') })
    expect(() => logger.error('boom')).not.toThrow()
  })

  test('限流：同 fingerprint 1 分钟内最多 3 次', () => {
    const reported = []
    logger.setReporter((ev) => reported.push(ev))
    for (let i = 0; i < 10; i++) logger.warn('repeat')
    expect(reported.length).toBe(3)
    // 不同 fingerprint 不受限
    logger.warn('different')
    expect(reported.length).toBe(4)
  })

  test('setEnv 影响事件 env 字段', () => {
    const reported = []
    logger.setReporter((ev) => reported.push(ev))
    logger.setEnv('prod')
    logger.error('oops')
    expect(reported[0].context.env).toBe('prod')
  })

  test('swallow 捕获异常并上报，返回 undefined', () => {
    const reported = []
    logger.setReporter((ev) => reported.push(ev))
    const ret = logger.swallow(() => { throw new Error('inner') }, 'do_thing', { orderId: 'o1' })
    expect(ret).toBeUndefined()
    expect(reported.length).toBe(1)
    expect(reported[0].level).toBe('error')
    expect(reported[0].message).toBe('do_thing')
    expect(reported[0].context.err).toBe('inner')
    expect(reported[0].context.orderId).toBe('o1')
  })

  test('swallow 正常返回值透传', () => {
    expect(logger.swallow(() => 42, 'tag')).toBe(42)
  })

  test('未知 level 降级为 info', () => {
    logger.log('lol', 'msg')
    expect(consoleCalls[0][0]).toBe('info')
  })

  test('getCurrentPages 抛异常时 page 字段为空字符串', () => {
    global.getCurrentPages = () => { throw new Error('no pages') }
    const reported = []
    logger.setReporter((ev) => reported.push(ev))
    logger.error('oops')
    expect(reported[0].context.page).toBe('')
  })
})
