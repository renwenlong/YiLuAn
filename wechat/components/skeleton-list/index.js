/**
 * skeleton-list — 列表骨架屏（P-08 review item）
 *
 * 替代 loading-overlay 在首次拉列表时全屏挡 UI 的体验：
 * 列表页首次加载（orders.length === 0 && loading）展示 N 个浅灰占位块，
 * 提示"内容正在到货"，避免用户对着白屏 + 转圈疑神疑鬼。
 *
 * Props:
 *   variant : 'order' | 'companion'   决定占位块的高度/形状
 *   count   : number                  占位条目数（默认 4）
 *
 * 设计要点：
 *  - 纯 wxml/wxss 实现，不依赖动画库；shimmer 通过 CSS keyframes 模拟
 *  - 单测：properties 默认值 + items 列表正确生成
 */
Component({
  options: { multipleSlots: false },
  properties: {
    variant: {
      type: String,
      value: 'order',
    },
    count: {
      type: Number,
      value: 4,
    },
  },
  data: {
    items: [0, 1, 2, 3],
  },
  observers: {
    count: function (n) {
      var size = Math.max(1, Math.min(10, parseInt(n, 10) || 4))
      var arr = []
      for (var i = 0; i < size; i++) arr.push(i)
      this.setData({ items: arr })
    },
  },
})
