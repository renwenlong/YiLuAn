import Foundation

struct Hospital: Codable, Identifiable {
    let id: String
    let name: String
    let address: String
    let level: String?
    let latitude: Double?
    let longitude: Double?
}
