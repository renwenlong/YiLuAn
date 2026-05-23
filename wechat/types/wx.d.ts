/**
 * Ambient type stub for the WeChat Mini Program `wx` global.
 *
 * Intentionally narrow — we only declare the methods we actually call in
 * checked files. Expand as the `include` whitelist in tsconfig.json grows.
 * Full official typings live in `miniprogram-api-typings` package; we avoid
 * pulling that in to keep the bootstrap zero-dep.
 */

declare const wx: {
  // navigation
  navigateTo(opts: { url: string; success?: Function; fail?: Function; complete?: Function }): void
  redirectTo(opts: { url: string; [k: string]: any }): void
  reLaunch(opts: { url: string; [k: string]: any }): void
  switchTab(opts: { url: string; [k: string]: any }): void
  navigateBack(opts?: { delta?: number; [k: string]: any }): void

  // storage
  getStorageSync(key: string): any
  setStorageSync(key: string, value: any): void
  removeStorageSync(key: string): void

  // tab bar / badges
  setTabBarBadge?(opts: { index: number; text: string; success?: Function; fail?: Function; complete?: Function }): void
  removeTabBarBadge?(opts: { index: number; success?: Function; fail?: Function; complete?: Function }): void
  showTabBarRedDot?(opts: { index: number; success?: Function; fail?: Function; complete?: Function }): void
  hideTabBarRedDot?(opts: { index: number; success?: Function; fail?: Function; complete?: Function }): void

  // haptic / system
  vibrateShort?(opts?: { type?: string; success?: Function; fail?: Function }): void
  vibrateLong?(opts?: { success?: Function; fail?: Function }): void

  // catchall — keep the door open for unchecked files
  [method: string]: any
}
