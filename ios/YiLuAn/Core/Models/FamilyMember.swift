import Foundation

/// [F-05] \u4ee3\u4ed6\u4eba\u4e0b\u5355\uff1a\u5bb6\u4eba\u6863\u6848\uff08\u540e\u7aef GET /api/v1/users/me/family-members\uff09
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
/// \u5168\u90e8 optional \u4ee5\u9002\u914d PATCH \u90e8\u5206\u66f4\u65b0\uff1bPOST \u65f6 name \u5fc5\u4f20\u3002
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
        ("parent", "\u7236\u6bcd"),
        ("spouse", "\u914d\u5076"),
        ("child", "\u5b50\u5973"),
        ("sibling", "\u5144\u5f1f\u59d0\u59b9"),
        ("grandparent", "\u7956\u7236\u6bcd"),
        ("relative", "\u4eb2\u621a"),
        ("friend", "\u670b\u53cb"),
        ("other", "\u5176\u4ed6"),
    ]

    private static let map: [String: String] = [
        "self": "\u672c\u4eba",
        "parent": "\u7236\u6bcd",
        "spouse": "\u914d\u5076",
        "child": "\u5b50\u5973",
        "sibling": "\u5144\u5f1f\u59d0\u59b9",
        "grandparent": "\u7956\u7236\u6bcd",
        "relative": "\u4eb2\u621a",
        "friend": "\u670b\u53cb",
        "other": "\u5176\u4ed6",
    ]

    static func label(for value: String?) -> String {
        guard let v = value, let label = map[v] else { return "\u5176\u4ed6" }
        return label
    }
}

enum FamilyGender: String, CaseIterable {
    case unknown
    case male
    case female

    var label: String {
        switch self {
        case .unknown: return "\u672a\u77e5"
        case .male: return "\u7537"
        case .female: return "\u5973"
        }
    }
}
