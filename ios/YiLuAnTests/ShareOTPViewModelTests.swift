import XCTest
@testable import YiLuAn

/// S2-INT-006 #1 · ShareOTPViewModel OTP 校验单测
/// 重点：OTP 必须严格等于 6 位（魈 #138 review 🟡 建议）
@MainActor
final class ShareOTPViewModelTests: XCTestCase {

    override func setUp() {
        super.setUp()
        // I18N-DEV-003B-7: 错误文案走 LocalizationManager.shared.t 抽 key 后,
        // 测试固定为中文以保证断言确定性(对齐 WalletViewModelTests 惯例)。
        LocalizationManager.shared.setLanguage(.zhHans)
    }

    override func tearDown() {
        LocalizationManager.shared.setLanguage(.zhHans)
        super.tearDown()
    }

    func testExchangeSessionRejectsOTPShorterThan6() async {
        let vm = ShareOTPViewModel(shareToken: "tok-abc")
        vm.phone = "13800000001"
        vm.otp = "123"  // < 6 位
        await vm.exchangeSession()
        if case .failure(let msg) = vm.stage {
            XCTAssertEqual(msg, "请输入 6 位验证码")
        } else {
            XCTFail("Expected failure for OTP < 6, got \(vm.stage)")
        }
    }

    func testExchangeSessionRejectsOTPLongerThan6() async {
        let vm = ShareOTPViewModel(shareToken: "tok-abc")
        vm.phone = "13800000001"
        vm.otp = "1234567"  // > 6 位
        await vm.exchangeSession()
        if case .failure(let msg) = vm.stage {
            XCTAssertEqual(msg, "请输入 6 位验证码")
        } else {
            XCTFail("Expected failure for OTP > 6, got \(vm.stage)")
        }
    }

    func testExchangeSessionRejectsEmptyOTP() async {
        let vm = ShareOTPViewModel(shareToken: "tok-abc")
        vm.phone = "13800000001"
        vm.otp = ""
        await vm.exchangeSession()
        if case .failure(let msg) = vm.stage {
            XCTAssertEqual(msg, "请输入 6 位验证码")
        } else {
            XCTFail("Expected failure for empty OTP, got \(vm.stage)")
        }
    }

    // MARK: - sendOTP 边界

    func testSendOTPRejectsEmptyPhone() async {
        let vm = ShareOTPViewModel(shareToken: "tok-abc")
        vm.phone = ""
        await vm.sendOTP()
        if case .failure(let msg) = vm.stage {
            XCTAssertEqual(msg, "请输入手机号")
        } else {
            XCTFail("Expected failure for empty phone, got \(vm.stage)")
        }
    }

    // MARK: - 本地脱敏 helper

    func testMaskPhoneFromValidNumber() {
        let vm = ShareOTPViewModel(shareToken: "tok-abc")
        XCTAssertEqual(vm.maskPhone("13812345678"), "138****5678")
        XCTAssertEqual(vm.maskPhone("18900001111"), "189****1111")
    }

    func testMaskPhoneFromShortReturnsAsIs() {
        let vm = ShareOTPViewModel(shareToken: "tok-abc")
        // < 7 字符不脱敏（防御性，避免暴露过短号码完整字面）
        XCTAssertEqual(vm.maskPhone("12345"), "12345")
    }

    // MARK: - reset

    func testResetToEnterPhoneClearsOTPAndStage() async {
        let vm = ShareOTPViewModel(shareToken: "tok-abc")
        vm.phone = "13800000001"
        vm.otp = "abcdef"
        vm.resetToEnterPhone()
        XCTAssertEqual(vm.otp, "")
        XCTAssertEqual(vm.stage, .enterPhone)
    }
}
