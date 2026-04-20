jest.mock('../../services/companion', () => ({
  getCompanionDetail: jest.fn(),
  getCompanionReviews: jest.fn(),
  getCompanions: jest.fn(),
}))
jest.mock('../../services/order', () => ({
  createOrder: jest.fn(),
}))
jest.mock('../../store/index', () => ({
  getState: jest.fn(() => ({})),
  setState: jest.fn(),
  subscribe: jest.fn(),
}))

var companionService = require('../../services/companion')

// Capture Page configs by overriding global.Page before requiring page modules
var detailConfig, createOrderConfig
;(function () {
  var configs = []
  global.Page = function (config) { configs.push(config) }
  require('../../pages/companion-detail/index')
  detailConfig = configs[0]
  configs.length = 0
  require('../../pages/patient/create-order/index')
  createOrderConfig = configs[0]
})()

function createPage(pageConfig) {
  var page = Object.assign({}, pageConfig, { data: Object.assign({}, pageConfig.data) })
  page.setData = function (obj) {
    Object.assign(this.data, obj)
  }
  return page
}

beforeEach(function () {
  jest.clearAllMocks()
  __resetWxStorage()
})

describe('companion-detail → create-order param consistency', function () {
  test('onBook navigates with companion_id param', function () {
    var page = createPage(detailConfig)
    page.companionId = 'test-companion-123'

    page.onBook()

    expect(wx.navigateTo).toHaveBeenCalledTimes(1)
    var url = wx.navigateTo.mock.calls[0][0].url
    expect(url).toContain('companion_id=test-companion-123')
    expect(url).not.toContain('companionId=')
  })

  test('create-order onLoad receives companion_id and loads companion', function () {
    companionService.getCompanionDetail.mockResolvedValue({
      id: 'comp-456',
      real_name: '张医生',
      avg_rating: 4.8,
      total_orders: 50,
      service_area: '北京协和医院',
    })

    var page = createPage(createOrderConfig)
    page.loadCompanion = createOrderConfig.loadCompanion.bind(page)
    page.onLoad = createOrderConfig.onLoad.bind(page)

    page.onLoad({ companion_id: 'comp-456' })

    expect(companionService.getCompanionDetail).toHaveBeenCalledWith('comp-456')
  })

  test('create-order onLoad without companion_id does not load companion', function () {
    var page = createPage(createOrderConfig)
    page.loadCompanion = createOrderConfig.loadCompanion.bind(page)
    page.onLoad = createOrderConfig.onLoad.bind(page)

    page.onLoad({})

    expect(companionService.getCompanionDetail).not.toHaveBeenCalled()
    expect(page.data.companionId).toBe('')
  })
})
