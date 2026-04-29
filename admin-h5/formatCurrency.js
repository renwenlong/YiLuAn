/**
 * formatCurrency — admin-h5
 *
 * Action #8: 统一金额展示为「千分位 + 两位小数」（¥1,200.00）。
 *
 * 注：任务原文建议落在 `admin-h5/src/utils/formatCurrency.ts`。
 *     当前 admin-h5 是「零构建 / Vanilla JS / 单页 HTML」架构（见 admin-h5/README.md），
 *     没有 src/ 目录、没有 TypeScript、没有打包器。
 *     为不破坏 MVP 架构，落在 admin-h5/formatCurrency.js（同目录、零依赖、浏览器 + Node 双跑）。
 *
 * 与 wechat/utils/formatCurrency.js 行为完全一致，便于跨端对齐。
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.formatCurrencyUtil = factory();
  }
})(typeof self !== 'undefined' ? self : this, function () {
  function formatCurrency(value, options) {
    var opts = options || {};
    var symbol = opts.symbol || '¥';
    var withSymbol = opts.withSymbol !== false;
    var unit = opts.unit || 'yuan';

    var num = Number(value);
    if (value === null || value === undefined || isNaN(num)) {
      return withSymbol ? symbol + '0.00' : '0.00';
    }
    if (unit === 'cent') num = num / 100;

    var negative = num < 0;
    var abs = Math.abs(num);
    var fixed = abs.toFixed(2);
    var parts = fixed.split('.');
    var withSep = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    var body = withSep + '.' + parts[1];
    var prefix = (negative ? '-' : '') + (withSymbol ? symbol : '');
    return prefix + body;
  }
  return { formatCurrency: formatCurrency };
});
