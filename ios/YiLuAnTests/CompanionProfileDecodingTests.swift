import XCTest
@testable import YiLuAn

/// P1-1: `CompanionProfile` 认证字段解码验证。
///
/// 关键不变量：
/// 1. 后端详情接口（`CompanionDetailResponse`）返回 snake_case
///    `certification_type` / `certification_no` / `certification_image_url` / `certified_at`
///    时，能解码到 model 对应字段（依赖 `keyDecodingStrategy = .convertFromSnakeCase`）。
/// 2. 后端列表接口（`CompanionListResponse`）**不返回**认证字段时，仍能解码成功
///    （所有 cert 字段均为可选，向后兼容）。
/// 3. `hasCertification` 计算属性与小程序 `wechat/pages/companion-detail/index.js`
///    判定逻辑一致：必须 type 和 imageUrl 都非空。
final class CompanionProfileDecodingTests: XCTestCase {

    private func makeDecoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }

    // MARK: - 详情接口（带认证字段）

    func testDecodeWithFullCertificationFields() throws {
        let json = """
        {
            "id": "cmp-1",
            "user_id": "usr-1",
            "real_name": "李四",
            "id_number": null,
            "certifications": null,
            "service_area": "海淀,朝阳",
            "avg_rating": 4.8,
            "total_orders": 23,
            "verification_status": "verified",
            "bio": "三甲医院在职护士",
            "avatar_url": null,
            "display_name": "李护士",
            "created_at": "2025-10-01T00:00:00Z",
            "certification_type": "三甲医院在职护士",
            "certification_no": "NUR-2025-0001",
            "certification_image_url": "https://cdn.example.com/cert/1.jpg",
            "certified_at": "2025-11-01T00:00:00Z"
        }
        """.data(using: .utf8)!

        let profile = try makeDecoder().decode(CompanionProfile.self, from: json)

        XCTAssertEqual(profile.certificationType, "三甲医院在职护士")
        XCTAssertEqual(profile.certificationNo, "NUR-2025-0001")
        XCTAssertEqual(profile.certificationImageUrl, "https://cdn.example.com/cert/1.jpg")
        XCTAssertNotNil(profile.certifiedAt)
        XCTAssertTrue(profile.hasCertification)
    }

    // MARK: - 列表接口（无认证字段，向后兼容）

    func testDecodeWithoutCertificationFields() throws {
        let json = """
        {
            "id": "cmp-2",
            "user_id": "usr-2",
            "real_name": "王五",
            "id_number": null,
            "certifications": null,
            "service_area": null,
            "avg_rating": 0.0,
            "total_orders": 0,
            "verification_status": "pending",
            "bio": null,
            "avatar_url": null,
            "display_name": null,
            "created_at": null
        }
        """.data(using: .utf8)!

        let profile = try makeDecoder().decode(CompanionProfile.self, from: json)

        XCTAssertNil(profile.certificationType)
        XCTAssertNil(profile.certificationNo)
        XCTAssertNil(profile.certificationImageUrl)
        XCTAssertNil(profile.certifiedAt)
        XCTAssertFalse(profile.hasCertification)
    }

    // MARK: - hasCertification 边界

    func testHasCertificationRequiresBothTypeAndImageUrl() throws {
        // 仅 type 非空 → false（与小程序逻辑对齐）
        let onlyType = """
        {
            "id": "x", "user_id": "x", "real_name": "x",
            "id_number": null, "certifications": null, "service_area": null,
            "avg_rating": 0, "total_orders": 0, "verification_status": "verified",
            "bio": null, "avatar_url": null, "display_name": null, "created_at": null,
            "certification_type": "护士",
            "certification_image_url": null
        }
        """.data(using: .utf8)!
        let p1 = try makeDecoder().decode(CompanionProfile.self, from: onlyType)
        XCTAssertFalse(p1.hasCertification)

        // 仅 image 非空 → false
        let onlyImage = """
        {
            "id": "x", "user_id": "x", "real_name": "x",
            "id_number": null, "certifications": null, "service_area": null,
            "avg_rating": 0, "total_orders": 0, "verification_status": "verified",
            "bio": null, "avatar_url": null, "display_name": null, "created_at": null,
            "certification_type": null,
            "certification_image_url": "https://x/y.jpg"
        }
        """.data(using: .utf8)!
        let p2 = try makeDecoder().decode(CompanionProfile.self, from: onlyImage)
        XCTAssertFalse(p2.hasCertification)
    }
}
