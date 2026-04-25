/**
 * app.json 分包 + 全局组件结构校验
 * - 主包页面数 ≤ 12（微信硬限 16，留余量）
 * - 分包总数 ≤ 20（微信硬限 20）
 * - 主包页 + 分包页 = 31（防漏配）
 * - subPackages.root 不能与主包 pages 路径重叠
 * - usingComponents 中的全局组件必须真实存在
 */
const fs = require('fs');
const path = require('path');

const APP_JSON = path.resolve(__dirname, '../../app.json');
const ROOT = path.resolve(__dirname, '../..');
const app = JSON.parse(fs.readFileSync(APP_JSON, 'utf8'));

describe('app.json 分包结构', () => {
  test('主包页数受控（≤ 12）', () => {
    expect(app.pages.length).toBeLessThanOrEqual(12);
  });

  test('分包数量未超微信上限（20）', () => {
    expect(app.subPackages.length).toBeLessThanOrEqual(20);
  });

  test('总页面数 = 主包 + 所有分包', () => {
    const total = app.pages.length +
      app.subPackages.reduce((acc, sp) => acc + sp.pages.length, 0);
    expect(total).toBe(31);
  });

  test('subPackages.root 与主包 pages 不重叠', () => {
    const mainSet = new Set(app.pages);
    for (const sp of app.subPackages) {
      for (const p of sp.pages) {
        const full = `${sp.root}/${p}`.replace(/\/+/g, '/');
        expect(mainSet.has(full)).toBe(false);
      }
    }
  });

  test('subPackages.name 唯一', () => {
    const names = app.subPackages.map(s => s.name);
    expect(new Set(names).size).toBe(names.length);
  });

  test('preloadRule 引用的分包名都存在', () => {
    const names = new Set(app.subPackages.map(s => s.name));
    for (const [page, rule] of Object.entries(app.preloadRule || {})) {
      for (const pkg of rule.packages) {
        expect(names.has(pkg)).toBe(true);
      }
    }
  });
});

describe('app.json 全局组件', () => {
  test('usingComponents 已注册 4 个高频组件', () => {
    const uc = app.usingComponents || {};
    expect(Object.keys(uc).sort()).toEqual([
      'companion-tab-bar',
      'empty-state',
      'loading-overlay',
      'patient-tab-bar',
    ]);
  });

  test('全局组件路径都存在 index.js', () => {
    for (const [, p] of Object.entries(app.usingComponents)) {
      const file = path.join(ROOT, p.replace(/^\//, '') + '.js');
      expect(fs.existsSync(file)).toBe(true);
    }
  });
});
