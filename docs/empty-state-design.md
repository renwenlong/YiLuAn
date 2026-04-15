# 空状态页面设计规范

> 用于订单列表为空、搜索无结果、消息列表为空等场景。

---

## 设计原则

1. **友好引导**：空状态不只是"没有数据"，而是引导用户下一步操作的机会
2. **一致性**：所有空状态使用统一的布局和样式
3. **使用 token**：颜色/字号/间距统一使用 `variables.wxss` 中定义的变量

## 布局规范

```
┌─────────────────────────────────┐
│                                 │
│           (留白 120rpx)          │
│                                 │
│         ┌───────────┐           │
│         │   图标     │           │
│         │  160rpx   │           │
│         └───────────┘           │
│                                 │
│       主标题 (32rpx, bold)       │
│    副标题/描述 (28rpx, hint)     │
│                                 │
│       ┌──────────────┐          │
│       │  操作按钮     │          │
│       └──────────────┘          │
│                                 │
└─────────────────────────────────┘
```

## 具体场景

### 1. 订单列表为空

- **图标**：📋 或自定义空订单 SVG
- **主标题**：暂无订单
- **副标题**：您还没有预约过陪诊服务
- **按钮**：去预约（跳转到首页浏览陪诊师）

### 2. 搜索无结果

- **图标**：🔍 或自定义搜索空 SVG
- **主标题**：未找到匹配结果
- **副标题**：试试其他关键词或筛选条件
- **按钮**：清除筛选

### 3. 消息列表为空

- **图标**：💬 或自定义消息空 SVG
- **主标题**：暂无消息
- **副标题**：有新的订单动态会通知您
- **按钮**：无

### 4. 陪诊师列表为空

- **图标**：👤 或自定义人物空 SVG
- **主标题**：附近暂无可用陪诊师
- **副标题**：请稍后再试或更换城市
- **按钮**：刷新

### 5. 评价列表为空

- **图标**：⭐ 或自定义星星空 SVG
- **主标题**：暂无评价
- **副标题**：完成陪诊服务后可以来评价
- **按钮**：无

## 样式规范（使用 CSS 变量）

```wxss
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--spacing-xl) var(--spacing-lg);
  padding-top: 120rpx;
}

.empty-state__icon {
  width: 160rpx;
  height: 160rpx;
  margin-bottom: var(--spacing-lg);
  opacity: 0.6;
}

.empty-state__title {
  font-size: var(--font-size-title);
  color: var(--color-text-primary);
  font-weight: bold;
  margin-bottom: var(--spacing-sm);
}

.empty-state__desc {
  font-size: var(--font-size-body);
  color: var(--color-text-hint);
  text-align: center;
  margin-bottom: var(--spacing-xl);
  line-height: 1.5;
}

.empty-state__action {
  min-width: 240rpx;
  height: 80rpx;
  line-height: 80rpx;
  font-size: var(--font-size-body);
  background-color: var(--color-primary);
  color: var(--color-text-white);
  border-radius: var(--radius-lg);
  text-align: center;
}
```

## 配色方案

| 元素 | 变量 | 色值 |
|------|------|------|
| 标题文字 | `--color-text-primary` | #333333 |
| 描述文字 | `--color-text-hint` | #999999 |
| 按钮背景 | `--color-primary` | #1890FF |
| 按钮文字 | `--color-text-white` | #FFFFFF |
| 页面背景 | `--color-bg-page` | #F5F5F5 |

---

**状态**：设计规范已定义，待创建具体图标资源并集成到小程序中。
