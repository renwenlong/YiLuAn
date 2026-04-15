import XCTest
@testable import YiLuAn

@MainActor
final class AuthViewModelTests: XCTestCase {

    var viewModel: AuthViewModel!

    override func setUp() {
        super.setUp()
        KeychainManager.clearTokens()
        viewModel = AuthViewModel()
    }

    override func tearDown() {
        KeychainManager.clearTokens()
        viewModel = nil
        super.tearDown()
    }

    func testInitialStateWithNoToken() {
        XCTAssertFalse(viewModel.isAuthenticated)
        XCTAssertNil(viewModel.currentUser)
        XCTAssertFalse(viewModel.isLoading)
        XCTAssertNil(viewModel.errorMessage)
    }

    func testInitialStateWithToken() {
        KeychainManager.accessToken = "test-token"
        let vm = AuthViewModel()
        XCTAssertTrue(vm.isAuthenticated)
    }

    func testSignOutClearsState() {
        viewModel.isAuthenticated = true
        viewModel.currentUser = User(
            id: "1", phone: "13800138000", role: .patient,
            displayName: "Test", avatarUrl: nil, createdAt: Date()
        )
        viewModel.signOut()

        XCTAssertFalse(viewModel.isAuthenticated)
        XCTAssertNil(viewModel.currentUser)
        XCTAssertNil(KeychainManager.accessToken)
        XCTAssertNil(KeychainManager.refreshToken)
    }

    func testSignOutClearsTokens() {
        KeychainManager.accessToken = "access"
        KeychainManager.refreshToken = "refresh"
        viewModel.signOut()

        XCTAssertNil(KeychainManager.accessToken)
        XCTAssertNil(KeychainManager.refreshToken)
    }

    func testIsLoadingDefaultsFalse() {
        XCTAssertFalse(viewModel.isLoading)
    }

    func testErrorMessageDefaultsNil() {
        XCTAssertNil(viewModel.errorMessage)
    }
}
