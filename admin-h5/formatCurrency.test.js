// Action #8 — formatCurrency tests for admin-h5 (no jest, runs via `node --test`)
const test = require('node:test');
const assert = require('node:assert/strict');
const { formatCurrency } = require('./formatCurrency.js');

test('整数 → 千分位', () => {
  assert.equal(formatCurrency(1200), '¥1,200.00');
  assert.equal(formatCurrency(0), '¥0.00');
  assert.equal(formatCurrency(299), '¥299.00');
});

test('小数补 / 截两位', () => {
  assert.equal(formatCurrency(1.5), '¥1.50');
  assert.equal(formatCurrency('1234.5'), '¥1,234.50');
  assert.equal(formatCurrency(0.1 + 0.2), '¥0.30');
});

test('大数千分位', () => {
  assert.equal(formatCurrency(1234567), '¥1,234,567.00');
  assert.equal(formatCurrency(1234567890.99), '¥1,234,567,890.99');
});

test('负数：- 在 ¥ 前', () => {
  assert.equal(formatCurrency(-50), '-¥50.00');
  assert.equal(formatCurrency(-1234.5), '-¥1,234.50');
});

test('null / undefined / NaN / 非法 → ¥0.00', () => {
  assert.equal(formatCurrency(null), '¥0.00');
  assert.equal(formatCurrency(undefined), '¥0.00');
  assert.equal(formatCurrency(NaN), '¥0.00');
  assert.equal(formatCurrency('abc'), '¥0.00');
});

test('字符串数字也支持', () => {
  assert.equal(formatCurrency('1200'), '¥1,200.00');
});

test('unit=cent → /100', () => {
  assert.equal(formatCurrency(120000, { unit: 'cent' }), '¥1,200.00');
  assert.equal(formatCurrency(99, { unit: 'cent' }), '¥0.99');
});

test('options.symbol / withSymbol', () => {
  assert.equal(formatCurrency(1200, { symbol: 'CNY ' }), 'CNY 1,200.00');
  assert.equal(formatCurrency(1200, { withSymbol: false }), '1,200.00');
  assert.equal(formatCurrency(null, { withSymbol: false }), '0.00');
});
