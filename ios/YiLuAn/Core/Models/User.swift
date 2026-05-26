import Foundation

enum UserRole: String, Codable {
    case patient
    case companion
}

struct User: Codable, Identifiable {
    let id: String
    let phone: String
    let role: UserRole?
    let displayName: String?
    let avatarUrl: String?
    let createdAt: Date
}

struct PatientProfile: Codable, Identifiable {
    let id: String
    let userId: String
    let emergencyContact: String?
    let emergencyPhone: String?
    let medicalNotes: String?
    let preferredHospitalId: String?
    let createdAt: Date?
    let updatedAt: Date?
}

struct CompanionProfile: Codable, Identifiable {
    let id: String
    let userId: String
    let realName: String
    let idNumber: String?
    let certifications: [String]?
    let serviceArea: String?
    let avgRating: Double
    let totalOrders: Int
    let verificationStatus: String
    let bio: String?
    let avatarUrl: String?
    let displayName: String?
    let createdAt: Date?

    // F-01 认证证件展示（后端 snake_case: certification_type / certification_no / certification_image_url / certified_at）
    // 全部使用可选类型，后端列表接口（CompanionListResponse）不返回这些字段仍能正常 decode，保证向后兼容。
    let certificationType: String?
    let certificationNo: String?
    let certificationImageUrl: String?
    let certifiedAt: Date?

    /// 与小程序 `hasCertification` 判定对齐：有认证类型且有证件图。
    var hasCertification: Bool {
        guard let type = certificationType, !type.isEmpty,
              let img = certificationImageUrl, !img.isEmpty
        else { return false }
        return true
    }
}

struct AvatarUploadResponse: Decodable {
    let avatarUrl: String
}

struct UpdatePatientProfileRequest: Encodable {
    let emergencyContact: String?
    let emergencyPhone: String?
    let medicalNotes: String?
    let preferredHospitalId: String?
}

struct UpdateCompanionProfileRequest: Encodable {
    let bio: String?
    let serviceArea: String?
}

struct ApplyCompanionRequest: Encodable {
    let realName: String
    let idNumber: String?
    let serviceArea: String?
    let bio: String?
}

struct UpdateDisplayNameRequest: Encodable {
    let displayName: String
}
