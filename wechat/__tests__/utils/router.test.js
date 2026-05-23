const router = require('../../utils/router')

describe('utils/router', () => {
  let calls
  beforeEach(() => {
    calls = []
    global.wx = {
      navigateTo: (o) => calls.push(['navigateTo', o]),
      redirectTo: (o) => calls.push(['redirectTo', o]),
      reLaunch: (o) => calls.push(['reLaunch', o]),
      switchTab: (o) => calls.push(['switchTab', o]),
      navigateBack: (o) => calls.push(['navigateBack', o]),
    }
    router._clearHooks()
  })
  afterEach(() => {
    router._clearHooks()
    delete global.wx
  })

  test('navigate / redirect / relaunch / switchTab / back forward to wx', () => {
    router.navigate({ url: '/a' })
    router.redirect({ url: '/b' })
    router.relaunch({ url: '/c' })
    router.switchTab({ url: '/d' })
    router.back({ delta: 2 })
    expect(calls).toEqual([
      ['navigateTo', { url: '/a' }],
      ['redirectTo', { url: '/b' }],
      ['reLaunch', { url: '/c' }],
      ['switchTab', { url: '/d' }],
      ['navigateBack', { delta: 2 }],
    ])
  })

  test('toLogin reLaunches to /pages/login/index and emits toLogin event', () => {
    const events = []
    router.onBeforeNavigate((action, opts) => events.push([action, opts]))
    router.toLogin('401')
    expect(calls).toEqual([['reLaunch', { url: '/pages/login/index' }]])
    // toLogin emits a single semantic event (not the underlying reLaunch),
    // so hooks can count forced logouts without double-counting nav events.
    expect(events).toEqual([['toLogin', { reason: '401' }]])
  })

  test('toLogin without reason defaults to "unknown"', () => {
    const events = []
    router.onBeforeNavigate((action, opts) => events.push([action, opts]))
    router.toLogin()
    expect(events[0]).toEqual(['toLogin', { reason: 'unknown' }])
  })

  test('hooks fire before wx call and exceptions are swallowed', () => {
    const seen = []
    router.onBeforeNavigate(() => { throw new Error('boom') })
    router.onBeforeNavigate((action, opts) => seen.push([action, opts]))
    router.navigate({ url: '/x' })
    expect(seen).toEqual([['navigateTo', { url: '/x' }]])
    expect(calls).toEqual([['navigateTo', { url: '/x' }]])
  })

  test('onBeforeNavigate returns unsubscribe', () => {
    const seen = []
    const off = router.onBeforeNavigate((a) => seen.push(a))
    router.navigate({ url: '/1' })
    off()
    router.navigate({ url: '/2' })
    expect(seen).toEqual(['navigateTo'])
  })

  test('back defaults options to {}', () => {
    router.back()
    expect(calls).toEqual([['navigateBack', {}]])
  })

  test('missing wx method is a no-op (does not throw)', () => {
    global.wx = {}
    expect(() => router.navigate({ url: '/safe' })).not.toThrow()
  })
})
