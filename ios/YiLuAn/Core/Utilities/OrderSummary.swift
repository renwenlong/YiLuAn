import Foundation

/// U-1 折叠式下单「摘要模板钉死表」唯一真源（iOS 端）
///
/// 真源：`docs/design/wireframes/U1-folding-stepper/README.md` §「摘要模板钉死表」
/// **与微信端 `wechat/utils/orderSummary.js` 逐字符一致互锁**（AC#13 / AC#25 必测）。
/// 禁止各端各自格式化。
///
/// 分隔符钉死：半角空格 + 全角圆点 U+00B7 + 半角空格 = " · "
/// （两侧各一个半角空格）。
enum OrderSummary {
    /// 钉死分隔符：两侧半角空格包裹的全角圆点（U+00B7）
    static let separator: String = " \u{00B7} "

    /// 星期映射：固定「周X」（周一…周日，非「星期X」）
    /// 与微信 `WEEK_LABELS` 同源：index 0 = 周日。i18n: orderSummary.week*。
    static var weekLabels: [String] {
        let loc = LocalizationManager.shared
        return [
            loc.t("orderSummary.weekSun"), loc.t("orderSummary.weekMon"), loc.t("orderSummary.weekTue"),
            loc.t("orderSummary.weekWed"), loc.t("orderSummary.weekThu"), loc.t("orderSummary.weekFri"),
            loc.t("orderSummary.weekSat"),
        ]
    }

    /// ① 服务类型：`{服务名} · ¥{价格}`
    /// 服务名取选项原文；价格为整数无小数（与微信 Math.round 同步语义）。
    static func summaryService(serviceName: String?, price: Decimal?) -> String {
        guard let name = serviceName, !name.isEmpty else { return "" }
        let raw = (price ?? 0) as NSDecimalNumber
        // 四舍五入到整数，与微信 Math.round(Number(price) || 0) 同语义
        let rounded = raw.rounding(
            accordingToBehavior: NSDecimalNumberHandler(
                roundingMode: .plain,
                scale: 0,
                raiseOnExactness: false,
                raiseOnOverflow: false,
                raiseOnUnderflow: false,
                raiseOnDivideByZero: false
            )
        )
        return name + separator + "¥" + rounded.stringValue
    }

    /// ② 医院：`{医院简称}` 或 `{医院简称} · {科室}`
    /// 科室可选：选了才拼 ` · {科室}`，未选则只显医院简称，**不显「· 未选科室」**。
    static func summaryHospital(hospitalName: String?, department: String?) -> String {
        guard let name = hospitalName, !name.isEmpty else { return "" }
        let dept = (department ?? "").trimmingCharacters(in: .whitespaces)
        return dept.isEmpty ? name : name + separator + dept
    }

    /// ③ 日期：`{YYYY-MM-DD} {周X} {上午|下午}`
    /// 日期固定 YYYY-MM-DD（补零）；星期固定「周X」；时段仅「上午」「下午」。
    /// 入参 `dateStr` 形如 "2026-06-03"；`period` 为 "上午" | "下午"。
    static func summaryDate(dateStr: String?, period: String?) -> String {
        guard let dateStr, !dateStr.isEmpty,
              let period, !period.isEmpty
        else { return "" }
        // 严格正则：4-2-2 数字 + 连字符（与微信 /^(\d{4})-(\d{2})-(\d{2})$/ 同源）
        let pattern = "^(\\d{4})-(\\d{2})-(\\d{2})$"
        guard let regex = try? NSRegularExpression(pattern: pattern),
              let match = regex.firstMatch(
                in: dateStr,
                range: NSRange(dateStr.startIndex..., in: dateStr)
              ),
              match.numberOfRanges == 4
        else { return "" }
        // 用 UTC 构造避免时区偏移影响星期计算（与微信 Date.UTC 同源）
        let ns = dateStr as NSString
        guard let year = Int(ns.substring(with: match.range(at: 1))),
              let month = Int(ns.substring(with: match.range(at: 2))),
              let day = Int(ns.substring(with: match.range(at: 3)))
        else { return "" }
        var comps = DateComponents()
        comps.year = year
        comps.month = month
        comps.day = day
        comps.timeZone = TimeZone(identifier: "UTC")
        var utcCal = Calendar(identifier: .gregorian)
        utcCal.timeZone = TimeZone(identifier: "UTC")!
        guard let date = utcCal.date(from: comps) else { return "" }
        // Foundation weekday: 1=Sunday..7=Saturday → WEEK_LABELS index = weekday-1
        let weekday = utcCal.component(.weekday, from: date)
        let weekLabel = weekLabels[weekday - 1]
        return dateStr + " " + weekLabel + " " + period
    }

    /// ④ 患者&陪诊师：`{患者首字}** · {关系} · {年龄}岁`
    /// 姓名脱敏：仅首字 + 两个 `*`；年龄整数 + 「岁」。
    /// 注意：与微信 `String(patientName).charAt(0)` 同源——取首个 character（含中文/emoji 单字符语义）。
    static func summaryPatient(
        patientName: String?,
        relation: String?,
        age: Int?
    ) -> String {
        guard let name = patientName, !name.isEmpty else { return "" }
        // 取首个 character（与 JS charAt(0) 在 BMP 中文上同语义）
        let firstChar = String(name.first!)
        let masked = firstChar + "**"
        // 与微信 Math.round(Number(age) || 0) 同源：nil → 0
        let a = max(0, age ?? 0)
        let rel = relation ?? ""
        return masked + separator + rel + separator + LocalizationManager.shared.t("orderSummary.ageYears", "\(a)")
    }
}
