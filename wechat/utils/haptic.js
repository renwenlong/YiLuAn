/**
 * haptic.js — P-03 触感反馈统一入口
 *
 * 封装 wx.vibrateShort 以便：
 * 1. 用户设置里关了触感 → 静默跳过
 * 2. 在 iOS 13+ / Android 普遍支持的 light 风格
 * 3. 调用失败不抛错（老设备 / 低版本基础库）
 */

const TYPES = ['light', 'medium', 'heavy'];

/**
 * @param {'light'|'medium'|'heavy'} [type='light']
 * @returns {Promise<boolean>} true=triggered, false=skipped/failed
 */
function haptic(type = 'light') {
  const safeType = TYPES.includes(type) ? type : 'light';

  // 检查用户设置
  try {
    const settings = wx.getStorageSync('user_settings') || {};
    if (settings.hapticDisabled === true) {
      return Promise.resolve(false);
    }
  } catch (e) {
    // storage 读失败，继续尝试触发
  }

  // 基础库兼容性检查
  if (typeof wx === 'undefined' || typeof wx.vibrateShort !== 'function') {
    return Promise.resolve(false);
  }

  return new Promise((resolve) => {
    try {
      wx.vibrateShort({
        type: safeType,
        success: () => resolve(true),
        fail: () => resolve(false),
      });
    } catch (e) {
      resolve(false);
    }
  });
}

/**
 * 快捷方法：按钮轻触反馈
 */
haptic.light = () => haptic('light');
haptic.medium = () => haptic('medium');
haptic.heavy = () => haptic('heavy');

module.exports = haptic;
module.exports.default = haptic;
module.exports.haptic = haptic;
