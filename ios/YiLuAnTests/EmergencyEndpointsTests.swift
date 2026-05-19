import XCTest
@testable import YiLuAn

/// [F-03] Verify emergency endpoints are wired correctly to backend routes.
final class EmergencyEndpointsTests: XCTestCase {

    func testListContactsEndpoint() {
        let ep = APIEndpoint.emergencyContacts
        XCTAssertEqual(ep.path, "emergency/contacts")
        XCTAssertEqual(ep.method, .get)
        XCTAssertTrue(ep.requiresAuth)
    }

    func testCreateContactEndpoint() {
        let ep = APIEndpoint.createEmergencyContact
        XCTAssertEqual(ep.path, "emergency/contacts")
        XCTAssertEqual(ep.method, .post)
        XCTAssertTrue(ep.requiresAuth)
    }

    func testUpdateContactEndpoint() {
        let ep = APIEndpoint.updateEmergencyContact(id: "abc")
        XCTAssertEqual(ep.path, "emergency/contacts/abc")
        XCTAssertEqual(ep.method, .put)
        XCTAssertTrue(ep.requiresAuth)
    }

    func testDeleteContactEndpoint() {
        let ep = APIEndpoint.deleteEmergencyContact(id: "xyz")
        XCTAssertEqual(ep.path, "emergency/contacts/xyz")
        XCTAssertEqual(ep.method, .delete)
        XCTAssertTrue(ep.requiresAuth)
    }

    func testHotlineEndpoint() {
        let ep = APIEndpoint.emergencyHotline
        XCTAssertEqual(ep.path, "emergency/hotline")
        XCTAssertEqual(ep.method, .get)
    }

    func testTriggerEventEndpoint() {
        let ep = APIEndpoint.triggerEmergencyEvent
        XCTAssertEqual(ep.path, "emergency/events")
        XCTAssertEqual(ep.method, .post)
        XCTAssertTrue(ep.requiresAuth)
    }

    func testEventsHistoryEndpoint() {
        let ep = APIEndpoint.emergencyEvents
        XCTAssertEqual(ep.path, "emergency/events")
        XCTAssertEqual(ep.method, .get)
        XCTAssertTrue(ep.requiresAuth)
    }

    func testHospitalExtraEndpoints() {
        XCTAssertEqual(APIEndpoint.hospitalFilters.path, "hospitals/filters")
        XCTAssertEqual(APIEndpoint.hospitalFilters.method, .get)
        XCTAssertEqual(APIEndpoint.nearestHospitalRegion.path, "hospitals/nearest-region")
    }

    // MARK: - Model

    func testTriggerRequestEncodesContactId() throws {
        let body = EmergencyTriggerRequest(orderId: "o1", contactId: "c1", hotline: false, location: nil)
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let data = try encoder.encode(body)
        let dict = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(dict["order_id"] as? String, "o1")
        XCTAssertEqual(dict["contact_id"] as? String, "c1")
        XCTAssertEqual(dict["hotline"] as? Bool, false)
    }

    func testTriggerRequestEncodesHotline() throws {
        let body = EmergencyTriggerRequest(orderId: "o1", contactId: nil, hotline: true, location: nil)
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let data = try encoder.encode(body)
        let dict = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(dict["hotline"] as? Bool, true)
        XCTAssertNil(dict["contact_id"])
    }
}
