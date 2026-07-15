import XCTest
@testable import YiLuAn

/// S2-INT-004 · 摘要模板钉死表逐字符单测（AC#25 / AC#13 互锁必测）
/// 真源：docs/design/wireframes/U1-folding-stepper/README.md §「摘要模板钉死表」
/// **与微信 `wechat/__tests__/utils/orderSummary.test.js` 逐 case 对齐**——
/// 任一字符不符 → fail，与 iOS 端互锁。
final class OrderSummaryTests: XCTestCase {

    override func setUp() {
        super.setUp()
        // I18N-DEV-003B-9: weekLabels/ageYears 走 loc.t, 固定 zh-Hans 保断言确定性(F类).
        LocalizationManager.shared.setLanguage(.zhHans)
    }

    override func tearDown() {
        LocalizationManager.shared.setLanguage(.zhHans)
        super.tearDown()
    }

    // MARK: - 分隔符（半角空格 + 全角圆点 U+00B7 + 半角空格）

    func testSeparatorIsSpacePlusMiddleDotPlusSpace() {
        XCTAssertEqual(OrderSummary.separator, " \u{00B7} ")
        XCTAssertEqual(OrderSummary.separator.count, 3)
        let scalars = Array(OrderSummary.separator.unicodeScalars)
        XCTAssertEqual(scalars[0].value, 0x20)
        XCTAssertEqual(scalars[1].value, 0x00B7)
        XCTAssertEqual(scalars[2].value, 0x20)
    }

    // MARK: - ① 服务类型 {服务名} · ¥{价格}

    func testServiceExampleFromPinnedTable() {
        XCTAssertEqual(
            OrderSummary.summaryService(serviceName: "全程陪诊", price: 299),
            "全程陪诊 \u{00B7} \u{00A5}299"
        )
        XCTAssertEqual(
            OrderSummary.summaryService(serviceName: "全程陪诊", price: 299),
            "全程陪诊 · ¥299"
        )
    }

    func testServicePriceRoundedToInteger() {
        // 299.0 → 299, 299.6 → 300（与微信 Math.round 同源）
        XCTAssertEqual(
            OrderSummary.summaryService(serviceName: "全程陪诊", price: Decimal(string: "299.0")!),
            "全程陪诊 · ¥299"
        )
        XCTAssertEqual(
            OrderSummary.summaryService(serviceName: "全程陪诊", price: Decimal(string: "299.6")!),
            "全程陪诊 · ¥300"
        )
    }

    func testServiceEmptyNameReturnsEmpty() {
        XCTAssertEqual(
            OrderSummary.summaryService(serviceName: "", price: 299),
            ""
        )
    }

    // MARK: - ② 医院 {医院简称}[· {科室}]

    func testHospitalWithoutDepartmentShowsHospitalOnly() {
        // 未选科室 → 只显医院简称，不显「· 未选科室」
        XCTAssertEqual(
            OrderSummary.summaryHospital(hospitalName: "市一院", department: ""),
            "市一院"
        )
        XCTAssertEqual(
            OrderSummary.summaryHospital(hospitalName: "市一院", department: nil),
            "市一院"
        )
    }

    func testHospitalWithDepartmentAppendsSeparator() {
        XCTAssertEqual(
            OrderSummary.summaryHospital(hospitalName: "市一院", department: "神经内科"),
            "市一院 \u{00B7} 神经内科"
        )
        XCTAssertEqual(
            OrderSummary.summaryHospital(hospitalName: "市一院", department: "神经内科"),
            "市一院 · 神经内科"
        )
    }

    // MARK: - ③ 日期 {YYYY-MM-DD} {周X} {上午|下午}

    func testDateExampleFromPinnedTable() {
        // 2026-06-03 是周三
        XCTAssertEqual(
            OrderSummary.summaryDate(dateStr: "2026-06-03", period: "上午"),
            "2026-06-03 周三 上午"
        )
    }

    func testWeekLabelIsZhouXNotXingqiX() {
        XCTAssertEqual(
            OrderSummary.summaryDate(dateStr: "2026-06-03", period: "下午"),
            "2026-06-03 周三 下午"
        )
        XCTAssertFalse(
            OrderSummary.summaryDate(dateStr: "2026-06-03", period: "下午").contains("星期")
        )
    }

    func testDatePaddingYYYYMMDD() {
        // 2026-01-05 是周一
        XCTAssertEqual(
            OrderSummary.summaryDate(dateStr: "2026-01-05", period: "上午"),
            "2026-01-05 周一 上午"
        )
    }

    func testInvalidDateReturnsEmpty() {
        XCTAssertEqual(OrderSummary.summaryDate(dateStr: "2026/06/03", period: "上午"), "")
        XCTAssertEqual(OrderSummary.summaryDate(dateStr: "", period: "上午"), "")
    }

    // MARK: - ④ 患者&陪诊师 {首字}** · {关系} · {年龄}岁

    func testPatientExampleFromPinnedTable() {
        XCTAssertEqual(
            OrderSummary.summaryPatient(patientName: "张三", relation: "母亲", age: 68),
            "张** \u{00B7} 母亲 \u{00B7} 68\u{5C81}"
        )
        XCTAssertEqual(
            OrderSummary.summaryPatient(patientName: "张三", relation: "母亲", age: 68),
            "张** · 母亲 · 68岁"
        )
    }

    func testPatientMaskAlwaysFirstCharPlusTwoStars() {
        // 脱敏仅首字 + 两个 *（不随姓名长度变）
        XCTAssertEqual(
            OrderSummary.summaryPatient(patientName: "张", relation: "母亲", age: 68),
            "张** · 母亲 · 68岁"
        )
        XCTAssertEqual(
            OrderSummary.summaryPatient(patientName: "欧阳娜娜", relation: "女儿", age: 20),
            "欧** · 女儿 · 20岁"
        )
    }

    func testPatientEmptyNameReturnsEmpty() {
        XCTAssertEqual(
            OrderSummary.summaryPatient(patientName: "", relation: "母亲", age: 68),
            ""
        )
    }
}
