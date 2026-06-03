import XCTest
@testable import YiLuAn

/// S2-INT-006 #1 · ShareOrderResponse 补充单测
/// 备注：scope=full / progress_only 闸门已在 APIEndpointTests 覆盖
/// · testShareOrderResponseDeserializesAndExcludesPII
/// · testShareOrderProgressOnlyScopeBlocksImages
/// 本文件只补充两点 unique 价值：PII 反射断言 + timeline 解码
final class ShareOrderResponseScopeGatingTests: XCTestCase {

    private var decoder: JSONDecoder {
        let d = JSONDecoder()
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        d.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let str = try container.decode(String.self)
            if let date = formatter.date(from: str) { return date }
            let noFrac = ISO8601DateFormatter()
            noFrac.formatOptions = [.withInternetDateTime]
            if let date = noFrac.date(from: str) { return date }
            throw DecodingError.dataCorruptedError(
                in: container,
                debugDescription: "Invalid ISO8601 date: \(str)"
            )
        }
        return d
    }

    // MARK: - PII 字段必须不存在（§2.5 脱敏）— 反射断言

    func testShareOrderResponseStructHasNoPIIFields() {
        // 通过 Mirror 反射 ShareOrderResponse 字段名，确保没有任何 PII 字段名
        let sample = ShareOrderResponse(
            orderId: UUID(),
            orderNumber: "x",
            status: "x",
            serviceType: "x",
            appointmentDate: "x",
            appointmentTime: "x",
            hospitalName: nil,
            patientNameMasked: nil,
            companion: nil,
            shareScope: .full,
            canViewImages: false,
            canViewAISummary: false,
            timeline: nil
        )
        let mirror = Mirror(reflecting: sample)
        let fieldNames = mirror.children.compactMap { $0.label }.map { $0.lowercased() }

        // 禁止字段（§2.5）
        let forbidden = ["patient_phone", "phone", "patient_id_card", "id_card", "medical_notes", "notes"]
        for f in forbidden {
            XCTAssertFalse(
                fieldNames.contains(f),
                "ShareOrderResponse 必须不含 PII 字段 '\(f)'（§2.5 脱敏）"
            )
        }
    }

    // MARK: - timeline 可选 + 解码

    func testShareOrderResponseDecodesTimeline() throws {
        let json = """
        {
          "order_id": "33333333-3333-3333-3333-333333333333",
          "order_number": "YLA20260603003",
          "status": "in_progress",
          "service_type": "full_accompany",
          "appointment_date": "2026-06-03",
          "appointment_time": "上午",
          "hospital_name": null,
          "patient_name_masked": null,
          "companion": null,
          "share_scope": "full",
          "can_view_images": true,
          "can_view_ai_summary": true,
          "timeline": [
            { "at": "2026-06-03T10:00:00.000Z", "event": "订单创建", "detail": null },
            { "at": "2026-06-03T10:15:00.000Z", "event": "已支付", "detail": "微信支付 ¥299" }
          ]
        }
        """.data(using: .utf8)!

        let r = try decoder.decode(ShareOrderResponse.self, from: json)
        XCTAssertEqual(r.timeline?.count, 2)
        XCTAssertEqual(r.timeline?.first?.event, "订单创建")
        XCTAssertNil(r.timeline?.first?.detail)
        XCTAssertEqual(r.timeline?.last?.detail, "微信支付 ¥299")
    }
}
