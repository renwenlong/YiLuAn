const store = require('../../store/index')

beforeEach(() => {
  store.reset()
})

describe('store', () => {
  // Test 20: default state
  test('initial state has isAuthenticated=false and user=null', () => {
    const state = store.getState()
    expect(state.isAuthenticated).toBe(false)
    expect(state.user).toBeNull()
  })

  // Test 21: setState merges
  test('setState merges partial state', () => {
    store.setState({ isAuthenticated: true })
    const state = store.getState()
    expect(state.isAuthenticated).toBe(true)
    expect(state.user).toBeNull()
  })

  // Test 22: subscribe is called on change
  test('subscribe listener is called on setState', () => {
    const listener = jest.fn()
    store.subscribe(listener)
    store.setState({ user: { id: 'u1' } })
    expect(listener).toHaveBeenCalledTimes(1)
    expect(listener).toHaveBeenCalledWith(
      expect.objectContaining({ user: { id: 'u1' } })
    )
  })

  // Test 23: unsubscribe
  test('unsubscribe removes listener', () => {
    const listener = jest.fn()
    const unsub = store.subscribe(listener)
    unsub()
    store.setState({ isAuthenticated: true })
    expect(listener).not.toHaveBeenCalled()
  })
})
