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
