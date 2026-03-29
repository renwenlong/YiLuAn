import Foundation

struct Review: Codable, Identifiable {
    let id: String
    let orderId: String
    let rating: Int
    let comment: String?
    let createdAt: Date

    // Populated
    let patientName: String?
}
