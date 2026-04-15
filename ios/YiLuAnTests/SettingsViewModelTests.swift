import XCTest
@testable import YiLuAn

@MainActor
final class SettingsViewModelTests: XCTestCase {

    var viewModel: SettingsViewModel!

    override func setUp() {
        super.setUp()
        viewModel = SettingsViewModel()
    }

    override func tearDown() {
        viewModel.cleanup()
        viewModel = nil
        super.tearDown()
    }

    // MARK: - OTP Tests

    func testOTPCountdownStartsAt60() {
        viewModel.startOTPCountdown()
        XCTAssertEqual(viewModel.otpCountdown, 60)

        // canSendOTP should be false while countdown active
        XCTAssertFalse(viewModel.canSendOTP)
    }

    func testCanSendOTPWhenCountdownIsZero() {
        viewModel.otpCountdown = 0
        viewModel.isSendingOTP = false
        XCTAssertTrue(viewModel.canSendOTP)
    }

    func testCannotSendOTPWhileSending() {
        viewModel.otpCountdown = 0
        viewModel.isSendingOTP = true
        XCTAssertFalse(viewModel.canSendOTP)
    }

    // MARK: - Press Countdown Tests

    func testPressCountdownStartsAt3() {
        viewModel.startPressCountdown()
        XCTAssertTrue(viewModel.isPressing)
        XCTAssertEqual(viewModel.pressCountdown, 3)
    }

    func testCancelPressResetsState() {
        viewModel.startPressCountdown()
        viewModel.cancelPress()

        XCTAssertFalse(viewModel.isPressing)
        XCTAssertEqual(viewModel.pressCountdown, 3)
    }

    // MARK: - Delete Account Validation

    func testCanDeleteRequiresAllConditions() {
        // Initially can't delete
        XCTAssertFalse(viewModel.canDelete)

        // Only code — still can't
        viewModel.otpCode = "123456"
        XCTAssertFalse(viewModel.canDelete)

        // Code + confirmed — can delete
        viewModel.isConfirmed = true
        XCTAssertTrue(viewModel.canDelete)

        // Short code — can't
        viewModel.otpCode = "12345"
        XCTAssertFalse(viewModel.canDelete)
    }

    func testCannotDeleteWhileDeleting() {
        viewModel.otpCode = "123456"
        viewModel.isConfirmed = true
        viewModel.isDeletingAccount = true
        XCTAssertFalse(viewModel.canDelete)
    }

    // MARK: - Cache

    func testCalculateCacheSize() {
        // Should not crash and should produce a string
        viewModel.calculateCacheSize()
        XCTAssertFalse(viewModel.cacheSize.isEmpty)
    }
}
