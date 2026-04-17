/**
 * Tests for wechat/app.js — 全局 notificationWs 初始化 + 订阅机制
 */

jest.mock('../services/notificationWs', () => ({
  connect: jest.fn(),
  disconnect: jest.fn(),
}))

jest.mock('../services/user', () => ({
  getMe: jest.fn(() => Promise.resolve({ id: 'u1' })),
}))

let appConfig
let notificationWs

beforeEach(() => {
  jest.resetModules()
  __resetWxStorage()
  // 捕获 App({...}) 参数
  global.App = jest.fn((cfg) => { appConfig = cfg })
  // 重新 require：这样 mock 和 app.js 拿到的是同一个 mock 模块实例
  notificationWs = require('../services/notificationWs')
  notificationWs.connect.mockClear()
  notificationWs.disconnect.mockClear()
  require('../app.js')
})

describe('app.js 全局 notificationWs 接线', () => {
  test('App() 被调用且暴露 connect/disconnectNotificationWs + subscribeNotification', () => {
    expect(global.App).toHaveBeenCalledTimes(1)
    expect(typeof appConfig.onLaunch).toBe('function')
    expect(typeof appConfig.connectNotificationWs).toBe('function')
    expect(typeof appConfig.disconnectNotificationWs).toBe('function')
    expect(typeof appConfig.subscribeNotification).toBe('function')
  })

  test('onLaunch 已登录时调用 notificationWs.connect', () => {
    const farFuture = Math.floor(Date.now() / 1000) + 3600
    const payload = Buffer.from(JSON.stringify({ exp: farFuture, sub: 'u1' })).toString('base64')
    const fakeJwt = 'h.' + payload + '.s'
    wx.setStorageSync('yiluan_access_token', fakeJwt)

    appConfig.onLaunch.call(appConfig)
    expect(notificationWs.connect).toHaveBeenCalledTimes(1)
  })

  test('onLaunch 未登录时不调用 connect', () => {
    appConfig.onLaunch.call(appConfig)
    expect(notificationWs.connect).not.toHaveBeenCalled()
  })

  test('disconnectNotificationWs 调用 service.disconnect 并重置 connected 标记', () => {
    appConfig.globalData.notificationWsConnected = true
    appConfig.disconnectNotificationWs()
    expect(notificationWs.disconnect).toHaveBeenCalledTimes(1)
    expect(appConfig.globalData.notificationWsConnected).toBe(false)
  })

  test('subscribeNotification 返回 unsubscribe 函数；订阅者在通知到来时被调用', () => {
    const cb = jest.fn()
    const unsub = appConfig.subscribeNotification(cb)
    expect(typeof unsub).toBe('function')

    appConfig.connectNotificationWs()
    const passedOptions = notificationWs.connect.mock.calls[0][0]
    passedOptions.onNotification({ type: 'new_order', order_id: 'o1' })

    expect(cb).toHaveBeenCalledWith({ type: 'new_order', order_id: 'o1' })

    unsub()
    passedOptions.onNotification({ type: 'x' })
    expect(cb).toHaveBeenCalledTimes(1)
  })

  test('connectNotificationWs 幂等：重复调用不会抛错，标记保持 true', () => {
    appConfig.connectNotificationWs()
    appConfig.connectNotificationWs()
    expect(appConfig.globalData.notificationWsConnected).toBe(true)
    expect(notificationWs.connect).toHaveBeenCalledTimes(2)
  })
})
