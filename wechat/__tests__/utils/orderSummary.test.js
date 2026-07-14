// orderSummary 逐字符测试 — S2-INT-003 AC#13
// 真源示例取自 docs/design/wireframes/U1-folding-stepper/README.md 摘要模板钉死表。
// 任一字符不符 → fail（与 iOS 端互锁）。

const {
  SEP,
  summaryService,
  summaryHospital,
  summaryDate,
  summaryPatient,
} = require('../../utils/orderSummary')

const i18n = require('../../utils/i18n')

describe('orderSummary 摘要模板钉死表（逐字符）', () => {
  test('分隔符为半角空格+全角圆点U+00B7+半角空格', () => {
    expect(SEP).toBe(' \u00B7 ')
    expect(SEP.length).toBe(3)
    expect(SEP.charCodeAt(0)).toBe(0x20)
    expect(SEP.charCodeAt(1)).toBe(0x00b7)
    expect(SEP.charCodeAt(2)).toBe(0x20)
  })

  describe('① 服务类型 {服务名} · ¥{价格}', () => {
    test('钉死表示例：全程陪诊 · ¥299', () => {
      expect(summaryService('全程陪诊', 299)).toBe('全程陪诊 \u00B7 \u00A5299')
      expect(summaryService('全程陪诊', 299)).toBe('全程陪诊 · ¥299')
    })
    test('价格整数无小数（299.0 → 299, 299.6 → 300）', () => {
      expect(summaryService('全程陪诊', 299.0)).toBe('全程陪诊 · ¥299')
      expect(summaryService('全程陪诊', 299.6)).toBe('全程陪诊 · ¥300')
    })
    test('服务名空 → 空串', () => {
      expect(summaryService('', 299)).toBe('')
    })
  })

  describe('② 医院 {医院简称}[· {科室}]', () => {
    test('未选科室 → 只显医院简称，不显「· 未选科室」', () => {
      expect(summaryHospital('市一院', '')).toBe('市一院')
      expect(summaryHospital('市一院', null)).toBe('市一院')
      expect(summaryHospital('市一院', undefined)).toBe('市一院')
    })
    test('选了科室 → 拼 · {科室}', () => {
      expect(summaryHospital('市一院', '神经内科')).toBe('市一院 \u00B7 神经内科')
      expect(summaryHospital('市一院', '神经内科')).toBe('市一院 · 神经内科')
    })
  })

  describe('③ 日期 {YYYY-MM-DD} {周X} {上午|下午}', () => {
    test('钉死表示例：2026-06-03 周三 上午', () => {
      expect(summaryDate('2026-06-03', '上午')).toBe('2026-06-03 周三 上午')
    })
    test('星期为「周X」非「星期X」', () => {
      // 2026-06-03 是周三
      expect(summaryDate('2026-06-03', '下午')).toBe('2026-06-03 周三 下午')
      expect(summaryDate('2026-06-03', '下午')).not.toContain('星期')
    })
    test('补零格式 YYYY-MM-DD', () => {
      // 2026-01-05 是周一
      expect(summaryDate('2026-01-05', '上午')).toBe('2026-01-05 周一 上午')
    })
    test('非法日期 → 空串', () => {
      expect(summaryDate('2026/06/03', '上午')).toBe('')
      expect(summaryDate('', '上午')).toBe('')
    })

    // I18N-DEV-002C：英文态钉死 `{YYYY-MM-DD} {Wed} {Morning|Afternoon}`（帝君拍 A1，与 iOS 对称互锁）
    describe('英文态 summaryDate（getCurrentLang=en）', () => {
      afterEach(() => {
        i18n.setLang('zh-Hans') // 复位，避免污染其他用例
      })

      test('钉死表英文示例：2026-06-03 Wed Morning', () => {
        i18n.setLang('en')
        expect(summaryDate('2026-06-03', '上午')).toBe('2026-06-03 Wed Morning')
      })

      test('下午 → Afternoon，周几英文缩写', () => {
        i18n.setLang('en')
        expect(summaryDate('2026-06-03', '下午')).toBe('2026-06-03 Wed Afternoon')
      })

      test('周一英文 Mon（getUTCDay 索引对齐）', () => {
        i18n.setLang('en')
        // 2026-01-05 是周一
        expect(summaryDate('2026-01-05', '上午')).toBe('2026-01-05 Mon Morning')
      })

      test('日期固定 YYYY-MM-DD 补零（跨端一致，英文不改日期格式）', () => {
        i18n.setLang('en')
        expect(summaryDate('2026-01-05', '下午')).toBe('2026-01-05 Mon Afternoon')
      })

      test('非法日期英文态同样返空串', () => {
        i18n.setLang('en')
        expect(summaryDate('2026/06/03', '上午')).toBe('')
        expect(summaryDate('', '上午')).toBe('')
      })
    })
  })

  describe('④ 患者&陪诊师 {首字}** · {关系} · {年龄}岁', () => {
    test('钉死表示例：张** · 母亲 · 68岁', () => {
      expect(summaryPatient('张三', '母亲', 68)).toBe('张** \u00B7 母亲 \u00B7 68\u5C81')
      expect(summaryPatient('张三', '母亲', 68)).toBe('张** · 母亲 · 68岁')
    })
    test('脱敏仅首字+两个*（不随姓名长度变）', () => {
      expect(summaryPatient('张', '母亲', 68)).toBe('张** · 母亲 · 68岁')
      expect(summaryPatient('欧阳娜娜', '女儿', 20)).toBe('欧** · 女儿 · 20岁')
    })
    test('年龄整数+岁', () => {
      expect(summaryPatient('张三', '父亲', 70.4)).toBe('张** · 父亲 · 70岁')
    })
  })
})
