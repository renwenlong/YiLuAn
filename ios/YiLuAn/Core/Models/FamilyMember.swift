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
    static let allCases: [(value: String, label: String)] = [
        ("parent", "父母"),
        ("spouse", "配偶"),
        ("child", "子女"),
        ("sibling", "兄弟姐妹"),
        ("grandparent", "祖父母"),
        ("relative", "亲戚"),
        ("friend", "朋友"),
        ("other", "其他"),
    ]

    private static let map: [String: String] = [
        "self": "本人",
        "parent": "父母",
        "spouse": "配偶",
        "child": "子女",
        "sibling": "兄弟姐妹",
        "grandparent": "祖父母",
        "relative": "亲戚",
        "friend": "朋友",
        "other": "其他",
    ]

    static func label(for value: String?) -> String {
        guard let v = value, let label = map[v] else { return "其他" }
        return label
    }
}

enum FamilyGender: String, CaseIterable {
    case unknown
    case male
    case female

    var label: String {
        switch self {
        case .unknown: return "未知"
        case .male: return "男"
        case .female: return "女"
        }
    }
}
