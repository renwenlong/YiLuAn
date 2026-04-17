/**
 * Tests for utils/badge - TabBar 角标与未读数联动工具
 * 覆盖：count>0 调 setTabBarBadge / count<=0 调 removeTabBarBadge /
 *       >99 展示 99+ / wx API 缺失时静默不报错
 */

const { syncTabBarBadge, MESSAGE_TAB_INDEX } = require('../../utils/badge')

describe('utils/badge.syncTabBarBadge', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  test('count > 0 时调用 wx.setTabBarBadge 并传入消息 tab index', () => {
    syncTabBarBadge(3)
    expect(wx.setTabBarBadge).toHaveBeenCalledTimes(1)
    const arg = wx.setTabBarBadge.mock.calls[0][0]
    expect(arg.index).toBe(MESSAGE_TAB_INDEX)
    expect(arg.text).toBe('3')
    expect(wx.removeTabBarBadge).not.toHaveBeenCalled()
  })

  test('count = 0 时调用 wx.removeTabBarBadge 清除角标', () => {
    syncTabBarBadge(0)
    expect(wx.removeTabBarBadge).toHaveBeenCalledTimes(1)
    expect(wx.setTabBarBadge).not.toHaveBeenCalled()
  })

  test('count > 99 时文本展示为 99+', () => {
    syncTabBarBadge(120)
    expect(wx.setTabBarBadge.mock.calls[0][0].text).toBe('99+')
  })

  test('wx.setTabBarBadge 不存在（未启用 tabBar）时不抛异常', () => {
    const original = wx.setTabBarBadge
    delete wx.setTabBarBadge
    expect(() => syncTabBarBadge(5)).not.toThrow()
    wx.setTabBarBadge = original
  })

  test('options.index 覆盖默认 tab index', () => {
    syncTabBarBadge(1, { index: 0 })
    expect(wx.setTabBarBadge.mock.calls[0][0].index).toBe(0)
  })
})
