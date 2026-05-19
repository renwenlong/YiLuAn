import XCTest
@testable import YiLuAn

/// [F-07] / Hospital extras endpoint wiring.
final class FollowupAndHospitalEndpointsTests: XCTestCase {

    // MARK: - F-07 Followup Reminders

    func testCreateFollowupReminderEndpoint() {
        let ep = APIEndpoint.createFollowupReminder(orderId: "abc-123")
        XCTAssertEqual(ep.path, "orders/abc-123/followup-reminders")
        XCTAssertEqual(ep.method, .post)
        XCTAssertTrue(ep.requiresAuth)
    }

    func testMyFollowupRemindersEndpoint() {
        let ep = APIEndpoint.myFollowupReminders
        XCTAssertEqual(ep.path, "orders/me/followup-reminders")
        XCTAssertEqual(ep.method, .get)
        XCTAssertTrue(ep.requiresAuth)
    }

    func testCancelFollowupReminderEndpoint() {
        let ep = APIEndpoint.cancelFollowupReminder(id: "r-9")
        XCTAssertEqual(ep.path, "orders/me/followup-reminders/r-9")
        XCTAssertEqual(ep.method, .delete)
        XCTAssertTrue(ep.requiresAuth)
    }

    // MARK: - FollowupReminder model

    func testFollowupReminderStatusLabels() {
        let mk: (String) -> FollowupReminder = { s in
            FollowupReminder(
                id: "x", userId: nil, orderId: "o", remindAt: Date(),
                status: s, attempts: 0, note: nil, sentAt: nil, createdAt: nil
            )
        }
        XCTAssertEqual(mk("pending").statusLabel, "待提醒")
        XCTAssertEqual(mk("sent").statusLabel, "已发送")
        XCTAssertEqual(mk("cancelled").statusLabel, "已取消")
        XCTAssertEqual(mk("failed").statusLabel, "发送失败")
        XCTAssertTrue(mk("pending").canCancel)
        XCTAssertFalse(mk("sent").canCancel)
    }

    // MARK: - Hospital extras

    func testHospitalSearchParamsQueryItems() {
        var p = HospitalSearchParams()
        p.keyword = "协和"
        p.province = "北京"
        p.city = "北京"
        p.level = "三甲"
        p.tag = "综合"
        p.page = 2
        p.pageSize = 30

        let names = p.queryItems.map { $0.name }
        XCTAssertEqual(Set(names), Set(["keyword", "province", "city", "level", "tag", "page", "page_size"]))
        let pageItem = p.queryItems.first { $0.name == "page" }
        XCTAssertEqual(pageItem?.value, "2")
    }

    func testHospitalSearchEmptyParamsOnlyHasPagination() {
        let p = HospitalSearchParams()
        let names = p.queryItems.map { $0.name }
        XCTAssertEqual(Set(names), Set(["page", "page_size"]))
    }

    func testHospitalTagListParsing() {
        let h = Hospital(
            id: "1", name: "测试", address: nil, level: "三甲",
            province: "北京", city: "北京", district: "东城",
            tags: "综合, 教学,儿科", latitude: nil, longitude: nil
        )
        XCTAssertEqual(h.tagList, ["综合", "教学", "儿科"])
    }
}
