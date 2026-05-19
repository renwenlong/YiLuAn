// 双角色用户列表显示：后端返回 `roles: "patient,companion"` 时，
// 前端必须渲染出 **全部** 角色 pill（之前只取了 split(',')[0] 导致丢失）。
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const appSrc = fs.readFileSync(path.join(__dirname, 'app.js'), 'utf8');

test('users 列表存在 roleList + rolesCell 多角色渲染', () => {
  // 新代码：roleList = u.roles.split(',') → map 成多个 pill
  assert.match(appSrc, /roleList/);
  assert.match(appSrc, /rolesCell/);
  // 应当 join 多个 statusPill
  assert.match(appSrc, /roleList\.map\(/);
  assert.match(appSrc, /statusPill\(r\)/);
});
