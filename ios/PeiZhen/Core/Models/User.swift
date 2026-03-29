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

struct PatientProfile: Codable {
    let userId: String
    let emergencyContact: String?
    let emergencyPhone: String?
    let medicalNotes: String?
    let preferredHospitalId: String?
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
}
