// Unit tests for skeleton-list component (P-08 review item)
describe('skeleton-list component', () => {
  let componentDef
  let instance

  function createInstance(props) {
    const data = Object.assign({}, componentDef.data)
    Object.keys(componentDef.properties).forEach(key => {
      data[key] = componentDef.properties[key].value
    })
    if (props) Object.assign(data, props)
    return {
      data: data,
      setData: jest.fn(function (obj) { Object.assign(this.data, obj) }),
    }
  }

  beforeAll(() => {
    global.Component = function (def) { componentDef = def }
    require('../../components/skeleton-list/index')
  })

  beforeEach(() => {
    instance = createInstance()
  })

  test('property defaults: variant="order", count=4', () => {
    expect(componentDef.properties.variant.value).toBe('order')
    expect(componentDef.properties.count.value).toBe(4)
  })

  test('items array seeded with 4 entries by default', () => {
    expect(instance.data.items).toEqual([0, 1, 2, 3])
  })

  test('observer regenerates items when count changes', () => {
    componentDef.observers.count.call(instance, 6)
    expect(instance.setData).toHaveBeenCalledWith({ items: [0, 1, 2, 3, 4, 5] })
  })

  test('observer clamps count to [1, 10]', () => {
    // count=0 是假值，落回默认 4
    componentDef.observers.count.call(instance, 0)
    expect(instance.setData).toHaveBeenLastCalledWith({ items: [0, 1, 2, 3] })
    componentDef.observers.count.call(instance, 99)
    expect(instance.setData).toHaveBeenLastCalledWith({
      items: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    })
    // 负数 → Math.max(1, ...) 免负
    componentDef.observers.count.call(instance, -3)
    expect(instance.setData).toHaveBeenLastCalledWith({ items: [0] })
  })

  test('observer falls back to default when count is non-numeric', () => {
    componentDef.observers.count.call(instance, 'abc')
    expect(instance.setData).toHaveBeenLastCalledWith({
      items: [0, 1, 2, 3],
    })
  })
})
