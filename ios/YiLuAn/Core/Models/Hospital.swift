import Foundation

/// 医院模型，与 backend `HospitalResponse` schema 1:1。
struct Hospital: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let address: String?
    let level: String?
    let province: String?
    let city: String?
    let district: String?
    /// 逗号分隔的标签，如 "综合,教学"
    let tags: String?
    let latitude: Double?
    let longitude: Double?

    /// 拆开的标签数组（便于 UI 渲染）
    var tagList: [String] {
        guard let tags = tags, !tags.isEmpty else { return [] }
        return tags.split(separator: ",").map { String($0).trimmingCharacters(in: .whitespaces) }
    }
}

/// 分页 list 响应（backend HospitalListResponse）。
struct HospitalListResponse: Decodable {
    let items: [Hospital]
    let total: Int
}

/// 筛选下拉选项（backend HospitalFiltersResponse）。
struct HospitalFiltersResponse: Decodable {
    let provinces: [String]
    let cities: [String]
    let districts: [String]
    let levels: [String]
    let tags: [String]
}

/// 最近省市（backend HospitalRegionResponse）。
struct HospitalRegionResponse: Decodable {
    let province: String?
    let city: String?
}

/// 搜索参数集合，便于 ViewModel 持有。
struct HospitalSearchParams: Equatable {
    var keyword: String = ""
    var province: String? = nil
    var city: String? = nil
    var district: String? = nil
    var level: String? = nil
    var tag: String? = nil
    var page: Int = 1
    var pageSize: Int = 20

    var queryItems: [URLQueryItem] {
        var items: [URLQueryItem] = []
        if !keyword.isEmpty { items.append(URLQueryItem(name: "keyword", value: keyword)) }
        if let p = province, !p.isEmpty { items.append(URLQueryItem(name: "province", value: p)) }
        if let c = city, !c.isEmpty { items.append(URLQueryItem(name: "city", value: c)) }
        if let d = district, !d.isEmpty { items.append(URLQueryItem(name: "district", value: d)) }
        if let l = level, !l.isEmpty { items.append(URLQueryItem(name: "level", value: l)) }
        if let t = tag, !t.isEmpty { items.append(URLQueryItem(name: "tag", value: t)) }
        items.append(URLQueryItem(name: "page", value: "\(page)"))
        items.append(URLQueryItem(name: "page_size", value: "\(pageSize)"))
        return items
    }
}
