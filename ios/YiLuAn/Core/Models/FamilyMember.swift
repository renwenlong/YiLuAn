import Foundation

/// [F-05] 代他人下单：家人档案（后端 GET /api/v1/users/me/family-members）
struct FamilyMember: Codable, Identifiable, Hashable {
    let id: String
    let userId: String
    let name: String
    let relation: String?
    let phone: String?
    let gender: String?
    let age: Int?
    let medicalNotes: String?
    let createdAt: Date?
    let updatedAt: Date?

    var relationLabel: String { FamilyRelation.label(for: relation) }
}

struct FamilyMemberListResponse: Decodable {
    let items: [FamilyMember]
    let total: Int
}

/// Request body for POST/PATCH /users/me/family-members.
/// 全部 optional 以适配 PATCH 部分更新；POST 时 name 必传。
struct FamilyMemberRequest: Encodable {
    var name: String?
    var relation: String?
    var phone: String?
    var gender: String?
    var age: Int?
    var medicalNotes: String?
}

/// Mirrors backend FamilyRelation enum.
enum FamilyRelation {
    /// relation code 列表(显示文案经 loc 字典, 避免 Model 层硬编码中文 C 盲区)
    static let allValues: [String] = [
        "parent", "spouse", "child", "sibling",
        "grandparent", "relative", "friend", "other",
    ]

    /// (value, 本地化 label) 对 —— label 运行时走字典(shared 单例, Model 无 @EnvironmentObject scope)
    static var allCases: [(value: String, label: String)] {
        allValues.map { ($0, label(for: $0)) }
    }

    static func label(for value: String?) -> String {
        let loc = LocalizationManager.shared
        guard let v = value else { return loc.t("relation.other") }
        return loc.t("relation.\(v)")
    }
}

enum FamilyGender: String, CaseIterable {
    case unknown
    case male
    case female

    var label: String {
        let loc = LocalizationManager.shared
        switch self {
        case .unknown: return loc.t("familyMembers.genderUnknown")
        case .male: return loc.t("familyMembers.genderMale")
        case .female: return loc.t("familyMembers.genderFemale")
        }
    }
}
