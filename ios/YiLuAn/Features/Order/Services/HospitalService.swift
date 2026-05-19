import Foundation

/// 医院搜索/筛选 Service，与 wechat `services/hospital.js` 对齐。
/// 端点：
/// - GET /hospitals          搜索（支持 keyword/province/city/district/level/tag/page）
/// - GET /hospitals/filters  下拉筛选项（按 province/city 级联）
/// - GET /hospitals/nearest-region  按经纬度返回最近省市
/// - GET /hospitals/{id}     详情
enum HospitalService {

    static func search(_ params: HospitalSearchParams) async throws -> HospitalListResponse {
        try await APIClient.shared.request(.hospitals, queryItems: params.queryItems)
    }

    /// 兼容旧调用方（PatientProfile / CreateOrder 老代码），直接返回 items。
    static func searchItems(_ params: HospitalSearchParams) async throws -> [Hospital] {
        try await search(params).items
    }

    static func filters(province: String? = nil, city: String? = nil) async throws -> HospitalFiltersResponse {
        var q: [URLQueryItem] = []
        if let p = province, !p.isEmpty { q.append(URLQueryItem(name: "province", value: p)) }
        if let c = city, !c.isEmpty { q.append(URLQueryItem(name: "city", value: c)) }
        return try await APIClient.shared.request(.hospitalFilters, queryItems: q)
    }

    static func nearestRegion(latitude: Double, longitude: Double) async throws -> HospitalRegionResponse {
        let q = [
            URLQueryItem(name: "latitude", value: String(latitude)),
            URLQueryItem(name: "longitude", value: String(longitude)),
        ]
        return try await APIClient.shared.request(.nearestHospitalRegion, queryItems: q)
    }
}
