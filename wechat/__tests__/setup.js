// Mock wx global object for Jest
const _storage = {}

global.wx = {
  // Storage
  getStorageSync(key) {
    return _storage[key] || ''
  },
  setStorageSync(key, value) {
    _storage[key] = value
  },
  removeStorageSync(key) {
    delete _storage[key]
  },

  // Network
  request: jest.fn(),
  uploadFile: jest.fn(),
  connectSocket: jest.fn(() => ({
    onOpen: jest.fn(),
    onMessage: jest.fn(),
    onClose: jest.fn(),
    onError: jest.fn(),
    send: jest.fn(),
    close: jest.fn(),
  })),

  // Auth
  login: jest.fn(),

  // Navigation
  reLaunch: jest.fn(),
  navigateTo: jest.fn(),
  navigateBack: jest.fn(),
  switchTab: jest.fn(),
  redirectTo: jest.fn(),

  // Payment
  requestPayment: jest.fn(),

  // UI
  showToast: jest.fn(),
  showLoading: jest.fn(),
  hideLoading: jest.fn(),
  showModal: jest.fn(),
  chooseImage: jest.fn(),
  previewImage: jest.fn(),
}

// __wxConfig mock
global.__wxConfig = { envVersion: 'develop' }

// Helper to reset storage between tests
global.__resetWxStorage = () => {
  Object.keys(_storage).forEach(k => delete _storage[k])
}

// Helper to mock wx.request with a response
global.__mockWxRequest = (statusCode, data) => {
  wx.request.mockImplementation((options) => {
    if (options.success) {
      options.success({ statusCode, data })
    }
  })
}

// Helper to mock wx.request failure
global.__mockWxRequestFail = (error) => {
  wx.request.mockImplementation((options) => {
    if (options.fail) {
      options.fail(error || { errMsg: 'request:fail' })
    }
  })
}

// Helper to mock wx.uploadFile with a response
global.__mockWxUploadFile = (statusCode, data) => {
  wx.uploadFile.mockImplementation((options) => {
    if (options.success) {
      var responseData = typeof data === 'string' ? data : JSON.stringify(data)
      options.success({ statusCode: statusCode, data: responseData })
    }
  })
}
