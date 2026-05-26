// R-07: companion/chat fetchConversations 必须并发三个 getOrders 请求（Promise.all），
// 不能串行链式，否则首屏延迟 3x。
jest.mock('../../services/order', () => ({
  getOrders: jest.fn(),
}))
jest.mock('../../utils/router', () => ({ navigate: jest.fn() }))

global.Page = global.Page || jest.fn()

const orderSvc = require('../../services/order')

function loadPage() {
  let cfg
  const orig = global.Page
  global.Page = (c) => { cfg = c }
  jest.isolateModules(() => {
    require('../../pages/companion/chat/index')
  })
  global.Page = orig
  return cfg
}

function createPage() {
  const cfg = loadPage()
  const page = Object.assign({}, cfg, {
    data: Object.assign({}, cfg.data),
  })
  page.setData = function (obj) { Object.assign(this.data, obj) }
  return page
}

describe('companion/chat fetchConversations (R-07 parallel)', () => {
  beforeEach(() => {
    orderSvc.getOrders.mockReset()
  })

  test('三个 getOrders 请求并发发起（在第一个 resolve 之前已全部 invoke）', async () => {
    // 三个请求都给一个手动控制的 promise
    const resolvers = []
    orderSvc.getOrders.mockImplementation(() =>
      new Promise((resolve) => { resolvers.push(resolve) })
    )

    const page = createPage()
    page.fetchConversations()

    // 关键断言：在任何一个 promise resolve 之前，三个调用都已经发出了
    expect(orderSvc.getOrders).toHaveBeenCalledTimes(3)
    expect(orderSvc.getOrders).toHaveBeenNthCalledWith(1, { status: 'accepted' })
    expect(orderSvc.getOrders).toHaveBeenNthCalledWith(2, { status: 'in_progress' })
    expect(orderSvc.getOrders).toHaveBeenNthCalledWith(3, { status: 'completed' })

    // resolve 所有再 flush
    resolvers.forEach((r) => r({ items: [] }))
    await new Promise((r) => setImmediate(r))

    expect(page.data.loading).toBe(false)
  })

  test('三类订单结果按 accepted / in_progress / completed 顺序拼接', async () => {
    orderSvc.getOrders
      .mockResolvedValueOnce({ items: [{ id: 'a1', patient_name: 'Alice', hospital_name: 'H1', status: 'accepted' }] })
      .mockResolvedValueOnce({ items: [{ id: 'p1', patient_name: 'Bob', hospital_name: 'H2', status: 'in_progress' }] })
      .mockResolvedValueOnce({ items: [{ id: 'c1', patient_name: 'Carol', hospital_name: 'H3', status: 'completed' }] })

    const page = createPage()
    page.fetchConversations()
    await new Promise((r) => setImmediate(r))
    await new Promise((r) => setImmediate(r))

    expect(page.data.conversations.map((c) => c.id)).toEqual(['a1', 'p1', 'c1'])
    expect(page.data.loading).toBe(false)
  })

  test('任一请求失败 -> loading 复位', async () => {
    orderSvc.getOrders
      .mockResolvedValueOnce({ items: [] })
      .mockRejectedValueOnce(new Error('boom'))
      .mockResolvedValueOnce({ items: [] })

    const page = createPage()
    page.fetchConversations()
    await new Promise((r) => setImmediate(r))
    await new Promise((r) => setImmediate(r))

    expect(page.data.loading).toBe(false)
  })
})
