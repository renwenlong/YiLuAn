// S2-REQ-003-P5a smoke test: admin-h5 ServicePackages module 存在 + ROUTES 注册
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const indexHtml = fs.readFileSync(
  path.join(__dirname, 'index.html'), 'utf8'
);
const appJs = fs.readFileSync(
  path.join(__dirname, 'app.js'), 'utf8'
);
const adminModulesJs = fs.readFileSync(
  path.join(__dirname, 'admin-modules.js'), 'utf8'
);

test('index.html 含 servicePackages nav + view + edit modal', () => {
  assert.match(indexHtml, /data-route="servicePackages"/);
  assert.match(indexHtml, /id="servicePackagesView"/);
  assert.match(indexHtml, /id="spTbody"/);
  assert.match(indexHtml, /id="spEditModal"/);
  assert.match(indexHtml, /id="spCreateBtn"/);
  assert.match(indexHtml, /id="spRefreshBtn"/);
});

test('app.js ROUTES 含 servicePackages 入口 + state.servicePackages 初始化', () => {
  assert.match(appJs, /servicePackages:\s*\{\s*view:\s*'#servicePackagesView'/);
  assert.match(appJs, /ServicePackages\.bind\(\);/);
  assert.match(appJs, /servicePackages:\s*\{\s*items:\s*\[\]/);
});

test('admin-modules.js 定义 ServicePackages module + 5 个 CRUD 方法', () => {
  assert.match(adminModulesJs, /^const ServicePackages = \{/m);
  // 关键方法存在
  assert.match(adminModulesJs, /async load\(\)/);
  assert.match(adminModulesJs, /render\(items\)/);
  assert.match(adminModulesJs, /bind\(\)/);
  assert.match(adminModulesJs, /openEdit\(row\)/);
  assert.match(adminModulesJs, /async submit\(\)/);
  // 端点路径
  assert.match(adminModulesJs, /\/api\/v1\/admin\/service-packages\//);
});

test('CRUD 端点覆盖 GET/POST/PATCH/DELETE', () => {
  // load: GET
  assert.match(adminModulesJs, /apiCall\('\/api\/v1\/admin\/service-packages\/'\)/);
  // create POST + edit PATCH + toggle PATCH + delete DELETE
  assert.match(adminModulesJs, /method:\s*'POST'/);
  assert.match(adminModulesJs, /method:\s*'PATCH'/);
  assert.match(adminModulesJs, /method:\s*'DELETE'/);
});

test('code 字段在编辑时禁用 (业务码不可改)', () => {
  assert.match(adminModulesJs, /\$\('#spFieldCode'\)\.disabled = !!row;/);
});

test('删除前 confirm + 软删提示历史订单不影响', () => {
  assert.match(adminModulesJs, /confirm\('确认删除此档位？\(软删，历史订单不受影响\)'\)/);
});
