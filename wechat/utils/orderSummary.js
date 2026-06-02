// orderSummary.js
// S2-INT-003 — U-1 折叠式下单「摘要模板钉死表」唯一真源（微信端）
//
// 真源：docs/design/wireframes/U1-folding-stepper/README.md §「摘要模板钉死表」
// 与 iOS 端逐字符一致互锁（AC#13 必测）。禁止各端各自格式化。
//
// 分隔符钉死：半角空格 + 全角圆点 U+00B7 + 半角空格 = " · "
// （两侧各一个半角空格）。

// 钉死分隔符：两侧半角空格包裹的全角圆点（U+00B7）
var SEP = ' \u00B7 '

// 星期映射：固定「周X」（周一…周日，非「星期X」）
var WEEK_LABELS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

// ① 服务类型：`{服务名} · ¥{价格}`
//   服务名取选项原文；价格为整数无小数。
function summaryService(serviceName, price) {
  if (!serviceName) return ''
  var p = Math.round(Number(price) || 0)
  return serviceName + SEP + '\u00A5' + p
}

// ② 医院：`{医院简称}` 或 `{医院简称} · {科室}`
//   科室可选：选了才拼 ` · {科室}`，未选则只显医院简称，
//   不显「· 未选科室」。
function summaryHospital(hospitalName, department) {
  if (!hospitalName) return ''
  var dept = department ? String(department).trim() : ''
  return dept ? hospitalName + SEP + dept : hospitalName
}

// ③ 日期：`{YYYY-MM-DD} {周X} {上午|下午}`
//   日期固定 YYYY-MM-DD（补零）；星期固定「周X」；时段仅「上午」「下午」。
//   入参 dateStr 形如 "2026-06-03"；period 为 "上午" | "下午"。
function summaryDate(dateStr, period) {
  if (!dateStr || !period) return ''
  var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(dateStr))
  if (!m) return ''
  // 用 UTC 构造避免时区偏移影响星期计算
  var d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])))
  var week = WEEK_LABELS[d.getUTCDay()]
  return m[0] + ' ' + week + ' ' + period
}

// ④ 患者&陪诊师：`{患者首字}** · {关系} · {年龄}岁`
//   姓名脱敏：仅首字 + 两个 *；年龄整数 + 「岁」。
function summaryPatient(patientName, relation, age) {
  if (!patientName) return ''
  var firstChar = String(patientName).charAt(0)
  var masked = firstChar + '**'
  var a = Math.round(Number(age) || 0)
  return masked + SEP + (relation || '') + SEP + a + '\u5C81'
}

module.exports = {
  SEP: SEP,
  WEEK_LABELS: WEEK_LABELS,
  summaryService: summaryService,
  summaryHospital: summaryHospital,
  summaryDate: summaryDate,
  summaryPatient: summaryPatient
}
