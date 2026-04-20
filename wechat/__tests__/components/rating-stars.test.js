// Unit tests for rating-stars component
describe('rating-stars component', () => {
  let componentDef
  let instance

  function createInstance(props) {
    // Simulate WeChat Component instance
    const data = Object.assign({}, componentDef.data)
    // Apply property defaults, then overrides
    Object.keys(componentDef.properties).forEach(key => {
      data[key] = componentDef.properties[key].value
    })
    if (props) {
      Object.assign(data, props)
    }
    const inst = {
      data: data,
      setData: jest.fn(function (obj) {
        Object.assign(this.data, obj)
      }),
      triggerEvent: jest.fn()
    }
    // Bind methods
    Object.keys(componentDef.methods).forEach(name => {
      inst[name] = componentDef.methods[name].bind(inst)
    })
    return inst
  }

  beforeAll(() => {
    // Capture Component definition
    global.Component = function (def) { componentDef = def }
    require('../../components/rating-stars/index')
  })

  beforeEach(() => {
    jest.useFakeTimers()
    instance = createInstance()
  })

  afterEach(() => {
    jest.useRealTimers()
  })

  test('defaults to 5 stars with value 0', () => {
    expect(instance.data.stars).toEqual([1, 2, 3, 4, 5])
    expect(instance.data.value).toBe(0)
  })

  test('tap updates rating when interactive', () => {
    instance.data.interactive = true
    instance.onStarTap({ currentTarget: { dataset: { value: 3 } } })
    expect(instance.data.value).toBe(3)
    expect(instance.triggerEvent).toHaveBeenCalledWith('change', { value: 3 })
  })

  test('tap is ignored when not interactive', () => {
    instance.onStarTap({ currentTarget: { dataset: { value: 3 } } })
    expect(instance.data.value).toBe(0)
    expect(instance.triggerEvent).not.toHaveBeenCalled()
  })

  test('animation class clears after timeout', () => {
    instance.data.interactive = true
    instance.onStarTap({ currentTarget: { dataset: { value: 4 } } })
    expect(instance.data.animatingStar).toBe(4)
    jest.advanceTimersByTime(300)
    expect(instance.data.animatingStar).toBe(0)
  })
})
