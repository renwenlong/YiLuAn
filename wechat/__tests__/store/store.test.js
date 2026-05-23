const store = require('../../store/index')

beforeEach(() => {
  store._clearAllListeners()
  store.reset()
})

describe('store (legacy API)', () => {
  test('initial state has isAuthenticated=false and user=null', () => {
    const state = store.getState()
    expect(state.isAuthenticated).toBe(false)
    expect(state.user).toBeNull()
  })

  test('setState merges partial state', () => {
    store.setState({ isAuthenticated: true })
    const state = store.getState()
    expect(state.isAuthenticated).toBe(true)
    expect(state.user).toBeNull()
  })

  test('subscribe listener is called on setState', () => {
    const listener = jest.fn()
    store.subscribe(listener)
    store.setState({ user: { id: 'u1' } })
    expect(listener).toHaveBeenCalledTimes(1)
    expect(listener).toHaveBeenCalledWith(
      expect.objectContaining({ user: { id: 'u1' } })
    )
  })

  test('unsubscribe removes listener', () => {
    const listener = jest.fn()
    const unsub = store.subscribe(listener)
    unsub()
    store.setState({ isAuthenticated: true })
    expect(listener).not.toHaveBeenCalled()
  })

  test('一个 listener 抛错不影响其他', () => {
    const a = jest.fn(() => { throw new Error('boom') })
    const b = jest.fn()
    store.subscribe(a)
    store.subscribe(b)
    store.setState({ user: { id: 'u2' } })
    expect(a).toHaveBeenCalled()
    expect(b).toHaveBeenCalled()
  })

  test('reset 触发所有 listener 并清空非 isAuthenticated/user 字段', () => {
    store.setState({ unreadCount: 5, user: { id: 'x' } })
    const listener = jest.fn()
    store.subscribe(listener)
    store.reset()
    expect(listener).toHaveBeenCalledWith({ isAuthenticated: false, user: null })
  })
})

describe('store (subscribeSelector)', () => {
  test('selector 返回值变化才触发 listener', () => {
    const listener = jest.fn()
    store.subscribeSelector(store.selectUser, listener)
    store.setState({ isAuthenticated: true }) // user 没变
    expect(listener).not.toHaveBeenCalled()
    store.setState({ user: { id: 'u1' } })
    expect(listener).toHaveBeenCalledTimes(1)
    expect(listener).toHaveBeenCalledWith({ id: 'u1' }, expect.objectContaining({ user: { id: 'u1' } }))
    store.setState({ user: { id: 'u1' } }) // 引用变了但值浅相等
    // 这里 user 是对象，新引用 → 浅比对返回 false → 触发
    // 我们专门测的是 selector 返回 primitive 时的去重；下面单独覆
  })

  test('selector 返回 primitive 时，重复 setState 同值不触发', () => {
    const listener = jest.fn()
    store.subscribeSelector(store.selectIsAuthenticated, listener)
    store.setState({ isAuthenticated: true })
    store.setState({ isAuthenticated: true })
    store.setState({ isAuthenticated: true, user: { id: 'u1' } })
    expect(listener).toHaveBeenCalledTimes(1)
    expect(listener).toHaveBeenCalledWith(true, expect.any(Object))
  })

  test('fireImmediately 立即用当前值触发一次', () => {
    store.setState({ unreadCount: 3 })
    const listener = jest.fn()
    store.subscribeSelector(store.selectUnreadCount, listener, { fireImmediately: true })
    expect(listener).toHaveBeenCalledTimes(1)
    expect(listener).toHaveBeenCalledWith(3, expect.any(Object))
  })

  test('subscribeSelector 返回 unsubscribe', () => {
    const listener = jest.fn()
    const off = store.subscribeSelector(store.selectIsAuthenticated, listener)
    store.setState({ isAuthenticated: true })
    expect(listener).toHaveBeenCalledTimes(1)
    off()
    store.setState({ isAuthenticated: false })
    expect(listener).toHaveBeenCalledTimes(1)
  })

  test('selector 抛错不传染其他订阅者', () => {
    const bad = () => { throw new Error('sel err') }
    const goodListener = jest.fn()
    store.subscribeSelector(bad, jest.fn())
    store.subscribeSelector(store.selectIsAuthenticated, goodListener)
    store.setState({ isAuthenticated: true })
    expect(goodListener).toHaveBeenCalledTimes(1)
  })

  test('listener 抛错不影响后续 setState', () => {
    const off = store.subscribeSelector(store.selectIsAuthenticated, () => { throw new Error('l err') })
    expect(() => store.setState({ isAuthenticated: true })).not.toThrow()
    off()
  })

  test('reset 后 selector listener 收到新值', () => {
    store.setState({ unreadCount: 5 })
    const listener = jest.fn()
    store.subscribeSelector(store.selectUnreadCount, listener)
    store.reset()
    expect(listener).toHaveBeenCalledTimes(1)
    expect(listener).toHaveBeenCalledWith(0, expect.any(Object))
  })

  test('_listenerCount 反映所有订阅者总数', () => {
    expect(store._listenerCount()).toBe(0)
    const off1 = store.subscribe(jest.fn())
    const off2 = store.subscribeSelector(store.selectUser, jest.fn())
    expect(store._listenerCount()).toBe(2)
    off1(); off2()
    expect(store._listenerCount()).toBe(0)
  })
})

describe('store selectors', () => {
  test('selectUnreadCount 默认 0', () => {
    expect(store.selectUnreadCount(store.getState())).toBe(0)
    store.setState({ unreadCount: 7 })
    expect(store.selectUnreadCount(store.getState())).toBe(7)
  })

  test('selectCity 默认 null', () => {
    expect(store.selectCity(store.getState())).toBeNull()
    store.setState({ city: '北京' })
    expect(store.selectCity(store.getState())).toBe('北京')
  })

  test('selectLastNotification 默认 null', () => {
    expect(store.selectLastNotification(store.getState())).toBeNull()
  })
})
