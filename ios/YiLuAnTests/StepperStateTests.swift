import XCTest
@testable import YiLuAn

/// S2-INT-004 · U-1 状态机 + 回改冲突判定单测（AC#25 互锁必测）
/// 真源：docs/design/wireframes/U1-folding-stepper/README.md §四/§五
/// **与微信 `wechat/__tests__/utils/stepperState.test.js` 逐 case 对齐**。
final class StepperStateTests: XCTestCase {

    override func setUp() {
        super.setUp()
        // I18N-DEV-003B-9: stepTitles/deptConflictToast 走 loc.t, 固定 zh-Hans 保断言确定性(F类, 对齐 WalletViewModelTests 惯例).
        LocalizationManager.shared.setLanguage(.zhHans)
    }

    override func tearDown() {
        LocalizationManager.shared.setLanguage(.zhHans)
        super.tearDown()
    }

    // MARK: - 步骤数与命名（钉死 4 步互锁）

    func testTotalStepsIsFour() {
        XCTAssertEqual(StepperState.totalSteps, 4)
    }

    func testStepTitlesI18nSameSourceKeysBothLanguages() {
        // AC#25 契约演进(PM裁定 d9f00f63): 从「字面逐字符一致」→「同源字典语义等价」。
        // iOS stepTitles 走 createOrder.step* (与微信同源 key), 各语言态文案一致。
        let loc = LocalizationManager.shared
        loc.setLanguage(.zhHans)
        XCTAssertEqual(
            StepperState.stepTitles,
            ["服务类型", "医院", "日期", "患者与陪诊师"]
        )
        loc.setLanguage(.en)
        XCTAssertEqual(
            StepperState.stepTitles,
            ["Service Type", "Hospital", "Date", "Patient & Companion"]
        )
        loc.setLanguage(.zhHans)
    }

    // MARK: - isStepFilled 各步完成判定

    func testStep1FilledWhenServiceTypePresent() {
        XCTAssertTrue(StepperState.isStepFilled(1, data: StepperData(serviceType: "full")))
        XCTAssertFalse(StepperState.isStepFilled(1, data: StepperData()))
    }

    func testStep2FilledWhenHospitalIdPresentDepartmentOptional() {
        XCTAssertTrue(StepperState.isStepFilled(2, data: StepperData(hospitalId: "h1")))
        XCTAssertTrue(StepperState.isStepFilled(2, data: StepperData(hospitalId: "h1", department: "")))
        XCTAssertFalse(StepperState.isStepFilled(2, data: StepperData()))
    }

    func testStep3RequiresBothDateAndPeriod() {
        XCTAssertTrue(StepperState.isStepFilled(3, data: StepperData(date: "2026-06-03", period: "上午")))
        XCTAssertFalse(StepperState.isStepFilled(3, data: StepperData(date: "2026-06-03")))
        XCTAssertFalse(StepperState.isStepFilled(3, data: StepperData(period: "上午")))
    }

    func testStep4AlwaysFillable() {
        XCTAssertTrue(StepperState.isStepFilled(4, data: StepperData()))
    }

    // MARK: - computeStepStates 三态计算

    func testInitialStateActiveCollapsedCollapsedCollapsed() {
        XCTAssertEqual(
            StepperState.computeStepStates(currentStep: 1, data: StepperData(), maxReachedStep: 1),
            [.active, .collapsed, .collapsed, .collapsed]
        )
    }

    func testStep1DoneStep2Active() {
        let data = StepperData(serviceType: "full")
        XCTAssertEqual(
            StepperState.computeStepStates(currentStep: 2, data: data, maxReachedStep: 2),
            [.done, .active, .collapsed, .collapsed]
        )
    }

    func testStep3ActiveWhen1And2Done() {
        let data = StepperData(serviceType: "full", hospitalId: "h1")
        XCTAssertEqual(
            StepperState.computeStepStates(currentStep: 3, data: data, maxReachedStep: 3),
            [.done, .done, .active, .collapsed]
        )
    }

    func testNavigateBackKeepsDownstreamDone() {
        // 回改：current 指回②，maxReached=4，③已填 → 下游保留 done
        let data = StepperData(serviceType: "full", hospitalId: "h1", date: "2026-06-03", period: "上午")
        XCTAssertEqual(
            StepperState.computeStepStates(currentStep: 2, data: data, maxReachedStep: 4),
            [.done, .active, .done, .done]
        )
    }

    // MARK: - canNavigateTo 回改可点判定

    func testCanNavigateToDoneStep() {
        XCTAssertTrue(StepperState.canNavigateTo(1, data: StepperData(serviceType: "full")))
    }

    func testCannotNavigateToUnfilledStep() {
        XCTAssertFalse(StepperState.canNavigateTo(2, data: StepperData()))
    }

    // MARK: - canSubmit / firstIncompleteStep

    func testCanSubmitWhenAllFourStepsFilled() {
        let data = StepperData(serviceType: "full", hospitalId: "h1", date: "2026-06-03", period: "下午")
        XCTAssertTrue(StepperState.canSubmit(data))
        XCTAssertEqual(StepperState.firstIncompleteStep(data), 0)
    }

    func testMissingHospitalCannotSubmit() {
        let data = StepperData(serviceType: "full", date: "2026-06-03", period: "下午")
        XCTAssertFalse(StepperState.canSubmit(data))
        XCTAssertEqual(StepperState.firstIncompleteStep(data), 2)
    }

    func testMissingDateFirstIncompleteIsStep3() {
        let data = StepperData(serviceType: "full", hospitalId: "h1")
        XCTAssertEqual(StepperState.firstIncompleteStep(data), 3)
    }

    // MARK: - checkDepartmentConflict 回改科室冲突（钉死）

    func testNoConflictWhenOriginalDepartmentEmpty() {
        XCTAssertEqual(
            StepperState.checkDepartmentConflict(oldDepartment: "", newDeptList: ["内科", "外科"]),
            .none
        )
        XCTAssertEqual(
            StepperState.checkDepartmentConflict(oldDepartment: nil, newDeptList: ["内科"]),
            .none
        )
    }

    func testNoConflictWhenOriginalDepartmentStillExists() {
        XCTAssertEqual(
            StepperState.checkDepartmentConflict(oldDepartment: "神经内科", newDeptList: ["神经内科", "外科"]),
            .none
        )
    }

    func testConflictWhenOriginalDepartmentMissing() {
        XCTAssertEqual(
            StepperState.checkDepartmentConflict(oldDepartment: "神经内科", newDeptList: ["内科", "外科"]),
            .cleared("神经内科")
        )
    }

    func testToastTextCharForCharIdenticalToWechat() {
        XCTAssertEqual(
            StepperState.departmentConflictToast(clearedDept: "神经内科"),
            "原科室\"神经内科\"在该院区不可用，已为您清空，请重新选择"
        )
    }
}
