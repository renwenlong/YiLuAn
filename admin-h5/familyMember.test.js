// [F-05] Smoke test: admin-h5 订单详情包含「实际就诊人」渲染逻辑
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const modulesSrc = fs.readFileSync(path.join(__dirname, 'admin-modules.js'), 'utf8');
const indexHtml = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');

test('admin-modules.js 暴露 renderFamilyMember 并映射全部 9 个 relation 枚举', () => {
  assert.match(modulesSrc, /renderFamilyMember/);
  // 9 个后端 FamilyRelation 枚举值 → 中文 label
  const expected = [
    ["self", "本人"],
    ["parent", "父母"],
    ["spouse", "配偶"],
    ["child", "子女"],
    ["sibling", "兄弟姐妹"],
    ["grandparent", "祖父母"],
    ["relative", "亲戚"],
    ["friend", "朋友"],
    ["other", "其他"],
  ];
  for (const [k, v] of expected) {
    assert.ok(
      modulesSrc.includes(`${k}: '${v}'`),
      `relation 映射缺失或不匹配: ${k} → ${v}`
    );
  }
});

test('admin-modules.js 在 open() / loadRaw() 中调用 renderFamilyMember', () => {
  assert.match(modulesSrc, /this\.renderFamilyMember\(data\)/);
});

test('index.html 包含 #orderFamilyMember 占位 DOM', () => {
  assert.match(indexHtml, /id="orderFamilyMember"/);
});
