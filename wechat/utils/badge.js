/**
 * 未读角标与 TabBar 联动工具（小程序端）。
 *
 * 设计目标：
 * - 把 `wx.setTabBarBadge` / `wx.removeTabBarBadge` 的调用细节从业务逻辑里剥离，
 *   使 app.js 的通知分发只需要「告诉工具当前未读数」。
 * - 对未启用 tabBar / API 不存在的环境保持静默（测试环境、未配置 tabBar 的项目）。
 *
 * 注：「消息」tab 当前项目未启用 tabBar；保留 index 常量以便后续启用 tabBar 时生效。
 */

const DEFAULT_MESSAGE_TAB_INDEX = 2

/**
 * 把未读数同步到 tabBar 角标。
 * @param {number} count 当前未读数；<=0 清除角标
 * @param {{index?: number}} [options] 可选：指定 tabBar index
 */
function syncTabBarBadge(count, options) {
  var index = (options && typeof options.index === 'number')
    ? options.index
    : DEFAULT_MESSAGE_TAB_INDEX
  try {
    if (typeof wx === 'undefined' || !wx) return
    if (count > 0) {
      if (typeof wx.setTabBarBadge === 'function') {
        wx.setTabBarBadge({
          index: index,
          text: count > 99 ? '99+' : String(count),
          fail: function () { /* 未启用 tabBar 时静默 */ },
        })
      }
    } else {
      if (typeof wx.removeTabBarBadge === 'function') {
        wx.removeTabBarBadge({
          index: index,
          fail: function () { /* 未启用 tabBar 时静默 */ },
        })
      }
    }
  } catch (e) {
    // ignore —— 工具层不向上抛
  }
}

module.exports = {
  syncTabBarBadge: syncTabBarBadge,
  MESSAGE_TAB_INDEX: DEFAULT_MESSAGE_TAB_INDEX,
}
