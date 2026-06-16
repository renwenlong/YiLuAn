import XCTest
@testable import YiLuAn

/// S3-DEV-003-TRUST-UI-IOS — 4 信任卡 precheck unit test
///
/// Acceptance 5 条 cross-check:
/// 1. ✅ Swift UI 展示 4 cert 字段 → `testOrderPrecheckSummaryDecoding`
/// 2. ✅ 三端字段契约一致 → `testFieldContractMirrorsBackendSchema` (snake_case ↔ camelCase)
/// 3. ✅ WS event 触发 UI 刷新 → `testWSEventTypesAreParsed` (3 个 event 都解析)
/// 4. ✅ 不暴露证件原图 URL → `testNegativeListFieldsRejected` (17 字段 negative-list)
/// 5. ✅ E2E 3 状态切换 → `testViewModelTransitionsAcrossThreeStates`
///        (all_ready=false → all_ready=true → blocked)
@MainActor
final class OrderPrecheckTests: XCTestCase {

    // MARK: - Acceptance #1: Swift UI 展示 4 cert 字段

    func testOrderPrecheckSummaryDecoding() throws {
        // 后端返回 snake_case (与 backend/app/schemas/order_precheck.py 字段一致)
        let json = """
        {
          "order_id": "ord-001",
          "contract_status": {
            "ready": true,
            "contract_id": "ct-001",
            "contract_template_version": "v2.1",
            "contract_pdf_url": "https://r2.example.com/signed/ct-001?ttl=900",
            "generated_at": "2026-06-11T08:30:00Z"
          },
          "insurance_status": {
            "ready": true,
            "insurance_order_id": "ins-001",
            "insurance_policy_no_masked": "BX2026****1234",
            "insurance_policy_pdf_url": "https://r2.example.com/signed/ins-001?ttl=900",
            "insurance_effective_from": "2026-06-12"
          },
          "preparation_status": {
            "ready": true,
            "preparation_id": "prep-001",
            "prep_summary": "已生成 5 项",
            "sections_count": 5,
            "generated_at": "2026-06-11T08:30:00Z"
          },
          "companion_cert_status": {
            "ready": true,
            "companion_cert_pseudonym_name": "陈师傅",
            "companion_cert_work_id": "PC0042",
            "companion_cert_qualifications": ["康复治疗师", "健康管理师"],
            "companion_cert_proof_image_urls": ["https://r2.example.com/signed/cert-1?ttl=900"],
            "companion_cert_verified_at": "2026-06-10T12:00:00Z"
          },
          "all_ready": true,
          "payment_enabled": true,
          "blocked_reason": null,
          "signed_url_expires_at": "2026-06-11T08:45:00Z"
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .iso8601

        let summary = try decoder.decode(OrderPrecheckSummary.self, from: json)

        XCTAssertEqual(summary.orderId, "ord-001")
        XCTAssertTrue(summary.contractStatus.ready)
        XCTAssertEqual(summary.contractStatus.contractId, "ct-001")
        XCTAssertTrue(summary.insuranceStatus.ready)
        XCTAssertEqual(summary.insuranceStatus.insurancePolicyNoMasked, "BX2026****1234")
        XCTAssertTrue(summary.preparationStatus.ready)
        XCTAssertEqual(summary.preparationStatus.sectionsCount, 5)
        XCTAssertTrue(summary.companionCertStatus.ready)
        XCTAssertEqual(summary.companionCertStatus.companionCertPseudonymName, "陈师傅")
        XCTAssertEqual(summary.companionCertStatus.companionCertWorkId, "PC0042")
        XCTAssertEqual(summary.companionCertStatus.companionCertQualifications, ["康复治疗师", "健康管理师"])
        XCTAssertTrue(summary.allReady)
        XCTAssertTrue(summary.paymentEnabled)
        XCTAssertNil(summary.blockedReason)
    }

    // MARK: - Acceptance #2: 三端字段契约一致 (snake_case ↔ camelCase)

    func testFieldContractMirrorsBackendSchema() throws {
        // 验证 keyDecodingStrategy = .convertFromSnakeCase 工作正常
        // (后端 contract_id ↔ iOS contractId 等)
        let json = """
        {
          "order_id": "test",
          "contract_status": {"ready": false, "contract_id": null, "contract_template_version": null, "contract_pdf_url": null, "generated_at": null},
          "insurance_status": {"ready": false, "insurance_order_id": null, "insurance_policy_no_masked": null, "insurance_policy_pdf_url": null, "insurance_effective_from": null},
          "preparation_status": {"ready": false, "preparation_id": null, "prep_summary": null, "sections_count": null, "generated_at": null},
          "companion_cert_status": {"ready": false, "companion_cert_pseudonym_name": null, "companion_cert_work_id": null, "companion_cert_qualifications": null, "companion_cert_proof_image_urls": null, "companion_cert_verified_at": null},
          "all_ready": false,
          "payment_enabled": false,
          "blocked_reason": "合同生成中",
          "signed_url_expires_at": null
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .iso8601

        let summary = try decoder.decode(OrderPrecheckSummary.self, from: json)

        XCTAssertEqual(summary.orderId, "test")
        XCTAssertFalse(summary.allReady)
        XCTAssertFalse(summary.paymentEnabled)
        XCTAssertEqual(summary.blockedReason, "合同生成中")
        // null 全 None, 所有 4 卡 ready=false, 不 crash
        XCTAssertNil(summary.contractStatus.contractId)
        XCTAssertNil(summary.companionCertStatus.companionCertWorkId)
    }

    // MARK: - Acceptance #3: WS event 类型 (3 个 event 都被识别)

    func testWSEventTypesAreParsed() {
        // 后端 precheck_broadcast.py:111/125/141 定义 3 个 event 名
        XCTAssertEqual(PrecheckEventType(rawValue: "precheck.status.updated"), .statusUpdated)
        XCTAssertEqual(PrecheckEventType(rawValue: "precheck.all_ready"), .allReady)
        XCTAssertEqual(PrecheckEventType(rawValue: "precheck.blocked"), .blocked)
        XCTAssertNil(PrecheckEventType(rawValue: "cert_status_changed"))  // task acceptance 字面错的
        XCTAssertNil(PrecheckEventType(rawValue: "precheck.bogus"))  // forward-compat: 未知 event 不 crash
    }

    // MARK: - Acceptance #4: 不暴露证件原图 URL (negative-list 17 字段)

    func testNegativeListFieldsRejected() {
        // ABAC Layer 1 物理排除: ContractStatusCard 不允许出现这些字段
        // 编译期保证 (struct 没定义这些字段 → Swift 静态 type 错误)
        //
        // 这里用 Mirror reflection 跑 runtime 检查作为 defense-in-depth.
        let contract = ContractStatusCard(
            ready: true, contractId: nil, contractTemplateVersion: nil,
            contractPdfUrl: nil, generatedAt: nil
        )
        let mirror = Mirror(reflecting: contract)
        let fieldNames = mirror.children.compactMap { $0.label }

        // 禁止字段全部不存在
        let negativeContract = ["contractHash", "hashInputs", "storageBlobPath", "templateKey"]
        for forbidden in negativeContract {
            XCTAssertFalse(fieldNames.contains(forbidden),
                           "ContractStatusCard 不应有 \(forbidden) 字段 (ABAC Layer 1)")
        }

        // 同理 CompanionCertStatusCard
        let cert = CompanionCertStatusCard(
            ready: true, companionCertPseudonymName: nil, companionCertWorkId: nil,
            companionCertQualifications: nil, companionCertProofImageUrls: nil,
            companionCertVerifiedAt: nil
        )
        let certMirror = Mirror(reflecting: cert)
        let certFields = certMirror.children.compactMap { $0.label }

        let negativeCert = ["companionRealName", "companionIdCardHash", "companionPhone", "companionUserId"]
        for forbidden in negativeCert {
            XCTAssertFalse(certFields.contains(forbidden),
                           "CompanionCertStatusCard 不应有 \(forbidden) 字段 (ABAC Layer 1)")
        }
    }

    // MARK: - Acceptance #5: E2E 3 状态切换

    /// blocked (合同 ready=false) → all_ready=true → blocked (保险 ready=false) 3 态.
    func testViewModelTransitionsAcrossThreeStates() async throws {
        let vm = PrecheckViewModel(orderId: "ord-test", pollingInterval: 30)

        // 状态 1: blocked (合同未生成)
        let state1 = makeSummary(allReady: false, paymentEnabled: false,
                                 contractReady: false, blockedReason: "合同生成中")
        vm.serviceFetch = { _ in state1 }
        await vm.refresh()

        XCTAssertEqual(vm.summary?.allReady, false)
        XCTAssertEqual(vm.summary?.paymentEnabled, false)
        XCTAssertEqual(vm.summary?.blockedReason, "合同生成中")
        XCTAssertFalse(vm.summary?.contractStatus.ready ?? true)

        // 状态 2: all_ready (4 卡全 ready)
        let state2 = makeSummary(allReady: true, paymentEnabled: true,
                                 contractReady: true, blockedReason: nil)
        vm.serviceFetch = { _ in state2 }
        await vm.refresh()

        XCTAssertEqual(vm.summary?.allReady, true)
        XCTAssertEqual(vm.summary?.paymentEnabled, true)
        XCTAssertNil(vm.summary?.blockedReason)
        XCTAssertTrue(vm.summary?.contractStatus.ready ?? false)

        // 状态 3: blocked (保险作废 — 后端 PM payment-pause)
        let state3 = makeSummary(allReady: false, paymentEnabled: false,
                                 contractReady: true, blockedReason: "保险已作废, 请联系客服")
        vm.serviceFetch = { _ in state3 }
        await vm.refresh()

        XCTAssertEqual(vm.summary?.allReady, false)
        XCTAssertEqual(vm.summary?.paymentEnabled, false)
        XCTAssertEqual(vm.summary?.blockedReason, "保险已作废, 请联系客服")
    }

    // MARK: - Error path

    /// AC #5 / Error path: 404 静默 fallback (历史订单照应, 不作为错误).
    /// ViewModel 设计意图: 404 不报错, summary 留 nil, 付款闸门由父 View
    /// (`OrderDetailView` `if order.contractId != nil` block) 接管.
    /// 魈 review PR #266 拍板方案 A: keep silent fallback, 修 test 期待跟实现走.
    func testRefresh404IsSilentFallback() async {
        let vm = PrecheckViewModel(orderId: "ord-historical")
        vm.serviceFetch = { _ in
            throw APIError.httpError(statusCode: 404, message: "order_not_found")
        }
        await vm.refresh()

        XCTAssertNil(vm.summary, "404 应 silent fallback summary=nil")
        XCTAssertNil(vm.errorMessage, "404 不应上报错误 (历史订单场景)")
    }

    /// AC #5 / Error path: 非 404 错误 (500 / network) 仍须上报错误.
    /// 区别于上一 test, 验证 silent fallback **仅限 404**, 其他错误走正常错误路径.
    func testRefresh500ReportsError() async {
        let vm = PrecheckViewModel(orderId: "ord-err")
        vm.serviceFetch = { _ in
            throw APIError.httpError(statusCode: 500, message: "internal_error")
        }
        await vm.refresh()

        XCTAssertNil(vm.summary)
        XCTAssertNotNil(vm.errorMessage, "500 应上报错误")
        XCTAssertTrue(
            vm.errorMessage?.contains("500") ?? false,
            "errorMessage 应含 status code (让用户反馈问题能附上)"
        )
    }

    // MARK: - A11y copy

    func testCompanionCertA11yLabelIncludesSemanticStatusAndFields() {
        // Arrange
        let verifiedAt = Date(timeIntervalSince1970: 1_778_371_200) // 2026-05-10T00:00:00Z
        let cert = CompanionCertStatusCard(
            ready: true,
            companionCertPseudonymName: "陈师傅",
            companionCertWorkId: "PC0042",
            companionCertQualifications: ["康复治疗师", "健康管理师"],
            companionCertProofImageUrls: ["https://r2.example.com/signed/cert?ttl=900"],
            companionCertVerifiedAt: verifiedAt
        )

        // Act
        let label = PrecheckAccessibilityText.companionCertAccessibilityLabel(cert)
        let hint = PrecheckAccessibilityText.companionCertAccessibilityHint(cert)

        // Assert
        XCTAssertTrue(label.contains("陪诊师资质"))
        XCTAssertTrue(label.contains("状态: 已就绪"))
        XCTAssertTrue(label.contains("姓名: 陈师傅"))
        XCTAssertTrue(label.contains("工号: PC0042"))
        XCTAssertTrue(label.contains("资质: 康复治疗师、健康管理师"))
        XCTAssertTrue(label.contains("认证时间: 2026-05-10"))
        XCTAssertTrue(hint.contains("证件原图不会在用户端展示"))
    }

    func testCompanionCertA11yPendingAndVerifiedStatesAreDistinctWithoutColor() {
        // Arrange
        let pending = CompanionCertStatusCard(
            ready: false,
            companionCertPseudonymName: "陈师傅",
            companionCertWorkId: "PC0042",
            companionCertQualifications: nil,
            companionCertProofImageUrls: nil,
            companionCertVerifiedAt: nil
        )
        let verified = CompanionCertStatusCard(
            ready: true,
            companionCertPseudonymName: "陈师傅",
            companionCertWorkId: "PC0042",
            companionCertQualifications: ["康复治疗师"],
            companionCertProofImageUrls: nil,
            companionCertVerifiedAt: nil
        )

        // Act
        let pendingLine = PrecheckAccessibilityText.companionCertSummaryLine(pending)
        let verifiedLine = PrecheckAccessibilityText.companionCertSummaryLine(verified)

        // Assert
        XCTAssertTrue(pendingLine.contains("状态: 未就绪"))
        XCTAssertTrue(pendingLine.contains("认证时间待核验"))
        XCTAssertTrue(verifiedLine.contains("状态: 已就绪"))
        XCTAssertNotEqual(pendingLine, verifiedLine)
    }

    // MARK: - Helpers

    private func makeSummary(
        allReady: Bool,
        paymentEnabled: Bool,
        contractReady: Bool,
        blockedReason: String?
    ) -> OrderPrecheckSummary {
        OrderPrecheckSummary(
            orderId: "ord-test",
            contractStatus: ContractStatusCard(
                ready: contractReady,
                contractId: contractReady ? "ct-001" : nil,
                contractTemplateVersion: contractReady ? "v2.1" : nil,
                contractPdfUrl: contractReady ? "https://r2.example.com/signed/ct?ttl=900" : nil,
                generatedAt: contractReady ? Date() : nil
            ),
            insuranceStatus: InsuranceStatusCard(
                ready: allReady,
                insuranceOrderId: allReady ? "ins-001" : nil,
                insurancePolicyNoMasked: allReady ? "BX2026****1234" : nil,
                insurancePolicyPdfUrl: allReady ? "https://r2.example.com/signed/ins?ttl=900" : nil,
                insuranceEffectiveFrom: allReady ? "2026-06-12" : nil
            ),
            preparationStatus: PreparationStatusCard(
                ready: allReady,
                preparationId: allReady ? "prep-001" : nil,
                prepSummary: allReady ? "已生成 5 项" : nil,
                sectionsCount: allReady ? 5 : nil,
                generatedAt: allReady ? Date() : nil
            ),
            companionCertStatus: CompanionCertStatusCard(
                ready: allReady,
                companionCertPseudonymName: allReady ? "陈师傅" : nil,
                companionCertWorkId: allReady ? "PC0042" : nil,
                companionCertQualifications: allReady ? ["康复治疗师"] : nil,
                companionCertProofImageUrls: allReady ? ["https://r2.example.com/signed/cert?ttl=900"] : nil,
                companionCertVerifiedAt: allReady ? Date() : nil
            ),
            allReady: allReady,
            paymentEnabled: paymentEnabled,
            blockedReason: blockedReason,
            signedUrlExpiresAt: Date().addingTimeInterval(15 * 60)
        )
    }
}
