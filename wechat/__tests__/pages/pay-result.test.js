// Tests for pay-result page

// Minimal Page mock for testing
function createPage(pageDef) {
  var instance = {
    data: Object.assign({}, pageDef.data),
    setData(obj) {
      Object.assign(instance.data, obj)
    }
  }
  // Bind methods
  Object.keys(pageDef).forEach(function (key) {
    if (typeof pageDef[key] === 'function' && key !== 'data') {
      instance[key] = pageDef[key].bind(instance)
    }
  })
  return instance
}

// Load the page definition
const pageDef = (function () {
  var captured = null
  var origPage = global.Page
  global.Page = function (def) { captured = def }
  require('../../pages/patient/pay-result/index')
  global.Page = origPage
  return captured
})()

beforeEach(() => {
  jest.clearAllMocks()
})

describe('pay-result page', () => {
  // Test: success state renders correctly
  test('onLoad with status=success sets correct data', () => {
    var page = createPage(pageDef)
    page.onLoad({ status: 'success', order_id: 'o1' })

    expect(page.data.status).toBe('success')
    expect(page.data.orderId).toBe('o1')
    expect(page.data.errorMsg).toBe('')
  })

  // Test: fail state renders correctly with error message
  test('onLoad with status=fail sets error message', () => {
    var page = createPage(pageDef)
    page.onLoad({
      status: 'fail',
      order_id: 'o2',
      msg: encodeURIComponent('余额不足')
    })

    expect(page.data.status).toBe('fail')
    expect(page.data.orderId).toBe('o2')
    expect(page.data.errorMsg).toBe('余额不足')
  })

  // Test: cancel state renders correctly
  test('onLoad with status=cancel sets correct data', () => {
    var page = createPage(pageDef)
    page.onLoad({ status: 'cancel', order_id: 'o3' })

    expect(page.data.status).toBe('cancel')
    expect(page.data.orderId).toBe('o3')
  })

  // Test: default status is success
  test('onLoad with no status defaults to success', () => {
    var page = createPage(pageDef)
    page.onLoad({})

    expect(page.data.status).toBe('success')
  })

  // Test: onViewOrder navigates to order detail
  test('onViewOrder redirects to order detail', () => {
    var page = createPage(pageDef)
    page.onLoad({ status: 'success', order_id: 'o1' })
    page.onViewOrder()

    expect(wx.redirectTo).toHaveBeenCalledWith({
      url: '/pages/patient/order-detail/index?id=o1'
    })
  })

  // Test: onViewOrder without orderId goes to orders list
  test('onViewOrder without orderId goes to orders list', () => {
    var page = createPage(pageDef)
    page.onLoad({ status: 'success' })
    page.onViewOrder()

    expect(wx.reLaunch).toHaveBeenCalledWith({
      url: '/pages/orders/index'
    })
  })

  // Test: onRetry navigates back with need_pay=1
  test('onRetry redirects to order detail with need_pay=1', () => {
    var page = createPage(pageDef)
    page.onLoad({ status: 'fail', order_id: 'o1' })
    page.onRetry()

    expect(wx.redirectTo).toHaveBeenCalledWith({
      url: '/pages/patient/order-detail/index?id=o1&need_pay=1'
    })
  })

  // Test: onGoHome navigates to patient home
  test('onGoHome launches patient home', () => {
    var page = createPage(pageDef)
    page.onLoad({ status: 'success', order_id: 'o1' })
    page.onGoHome()

    expect(wx.reLaunch).toHaveBeenCalledWith({
      url: '/pages/patient/home/index'
    })
  })
})
