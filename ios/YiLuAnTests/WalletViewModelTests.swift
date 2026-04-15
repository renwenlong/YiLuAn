import XCTest
@testable import YiLuAn

@MainActor
final class WalletViewModelTests: XCTestCase {

    var viewModel: WalletViewModel!

    override func setUp() {
        super.setUp()
        viewModel = WalletViewModel()
    }

    override func tearDown() {
        viewModel = nil
        super.tearDown()
    }

    func testInitialState() {
        XCTAssertNil(viewModel.summary)
        XCTAssertTrue(viewModel.transactions.isEmpty)
        XCTAssertFalse(viewModel.isLoading)
        XCTAssertNil(viewModel.errorMessage)
        XCTAssertEqual(viewModel.total, 0)
    }

    func testWalletSummaryDecoding() throws {
        let json = """
        {
            "balance": 1000.50,
            "total_income": 5000.00,
            "withdrawn": 3999.50
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let summary = try decoder.decode(WalletSummary.self, from: json)

        XCTAssertEqual(summary.balance, 1000.50)
        XCTAssertEqual(summary.totalIncome, 5000.00)
        XCTAssertEqual(summary.withdrawn, 3999.50)
    }

    func testWalletTransactionTypeLabels() throws {
        let paymentJSON = """
        {"id":"1","type":"payment","amount":299.00,"description":"全程陪诊","created_at":"2026-04-15T10:00:00Z"}
        """.data(using: .utf8)!

        let incomeJSON = """
        {"id":"2","type":"income","amount":299.00,"description":"订单收入","created_at":"2026-04-15T10:00:00Z"}
        """.data(using: .utf8)!

        let refundJSON = """
        {"id":"3","type":"refund","amount":149.50,"description":"退款","created_at":"2026-04-15T10:00:00Z"}
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .iso8601

        let payment = try decoder.decode(WalletTransaction.self, from: paymentJSON)
        let income = try decoder.decode(WalletTransaction.self, from: incomeJSON)
        let refund = try decoder.decode(WalletTransaction.self, from: refundJSON)

        XCTAssertEqual(payment.typeLabel, "支付")
        XCTAssertEqual(payment.amountPrefix, "-")
        XCTAssertEqual(income.typeLabel, "收入")
        XCTAssertEqual(income.amountPrefix, "+")
        XCTAssertEqual(refund.typeLabel, "退款")
        XCTAssertEqual(refund.amountPrefix, "+")
    }

    func testTransactionListResponseDecoding() throws {
        let json = """
        {
            "items": [],
            "total": 15
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .iso8601
        let response = try decoder.decode(WalletTransactionListResponse.self, from: json)

        XCTAssertEqual(response.total, 15)
        XCTAssertTrue(response.items.isEmpty)
    }
}
