// P-07: 统一空状态组件，新增 hint 属性以兼容 chat / orders / 钱包等场景
Component({
  properties: {
    text: {
      type: String,
      value: '暂无数据'
    },
    hint: {
      type: String,
      value: ''
    },
    icon: {
      type: String,
      value: '空'
    }
  }
})
